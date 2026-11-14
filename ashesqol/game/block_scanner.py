"""Background scanner that finds chosen block types in the loaded chunks (read-only).

Memory layout (Bedrock 1.26.63, see docs/recon-1.26.63.md):
  LevelChunk (no vtable, pooled at a fixed stride)
    +member_offset: member object with a known vtable  -> used to find/validate chunks
    +pos:           ChunkPos (int x, int z)
    +sections:      std::vector<SubChunk> (entry size section_size; 24 in the overworld)
  SubChunk +layer0 / +layer1: SubChunkBlockStorage* (layer1 = water/waterlogging)
  Storage: vtable selects bits/block. Packed u32 words at +words, index = x*256 + z*16 + y,
           then (8-aligned) palette of Block* with capacity 2^bits, then the palette size (u64).
           Uniform storage (0 bits): one Block* at +words.
  Block +legacy -> BlockLegacy, whose std::string at +name is e.g. "minecraft:diamond_block".

Finding chunks: one full memory search for the member vtable (~30 s) locates the chunk pools;
after that only those pools are re-read each cycle (plus a margin to catch growth).
"""
import logging
import math
import struct
import threading
import time
from dataclasses import dataclass

from ..core.memory import find_qword
from .blocks import short_id
from .state import BlockHit

log = logging.getLogger(__name__)

CYCLE_SECONDS = 1.0
POOL_MERGE_GAP = 64             # slots: pool hits closer than this are treated as one run
DISCOVERY_MARGIN = 8            # also check this many slots past each run (pools grow)
DISCOVERY_SECONDS = 10.0        # look for newly loaded chunks this often; known ones are reused in between
FULL_SCAN_COOLDOWN = 60.0       # seconds between full searches for chunk pools
MISSING_CYCLES_FOR_RESCAN = 5   # player's own chunk not found this many cycles -> search again
MAX_HITS = 20000
MAX_RADIUS_CHUNKS = 12


def _h(v) -> int:
    return int(v, 16) if isinstance(v, str) else int(v)


@dataclass
class Layout:
    bits: int
    words: int          # number of u32 words
    palette: int        # palette offset from the storage object
    capacity: int


class BlockScanner:
    def __init__(self, pm, base: int, offsets: dict):
        self.pm = pm
        self.base = base
        c, s, b = offsets["chunk"], offsets["block_storage"], offsets["block"]
        self.member_vt = base + _h(c["member_vtable"])
        self.member_off = _h(c["member_offset"])
        self.stride = _h(c["stride"])
        self.pos_off = _h(c["pos"])
        self.dim_off = _h(c["dimension"]) if "dimension" in c else None
        self.sections_off = _h(c["sections"])
        self.section_size = _h(c["section_size"])
        self.layer_offs = [_h(c["layer0"]), _h(c["layer1"])]
        self.words_off = _h(s["words"])
        self.block_vt = base + _h(b["vtable"])
        self.legacy_off = _h(b["legacy"])
        self.name_off = _h(b["name"])
        self.known_layouts = {base + _h(vt): int(bits) for vt, bits in s.get("layouts", {}).items()}

        # inputs (set from the UI thread)
        self.wanted: frozenset[str] = frozenset()
        self.center: tuple[float, float, float] | None = None
        self.radius_blocks = 64.0
        self.dimension: int | None = None    # player's Dimension*; only chunks of this dimension are used

        # outputs (replaced atomically by the worker)
        self.hits: list[BlockHit] = []
        self.status = "starting..."

        self._layouts: dict[int, Layout | None] = {}
        self._names: dict[int, str] = {}       # Block* -> short id
        self._good_blocks: set[int] = set()    # Block* already checked against the Block vtable
        self._decoded: dict[int, tuple] = {}    # storage -> (words bytes, palette, wanted, origin, hits)
        self._seen: set[int] = set()
        self._pools: list[tuple[int, int]] = []  # (first slot address, slot count)
        self._known: dict[tuple[int, int], int] = {}   # ChunkPos -> chunk, for our dimension
        self._known_dimension = None
        self._last_discovery = -DISCOVERY_SECONDS
        self._last_full_scan = -FULL_SCAN_COOLDOWN
        self._missing = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="block-scanner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    # --- reads -----------------------------------------------------------------------
    def _q(self, addr: int) -> int:
        return self.pm.read_ulonglong(addr)

    def _string(self, addr: int) -> str:
        size, cap = struct.unpack("<QQ", self.pm.read_bytes(addr + 0x10, 16))
        if size > 200:
            return ""
        data = self.pm.read_bytes(addr, size) if cap < 16 else self.pm.read_bytes(self._q(addr), size)
        return data.decode(errors="replace")

    def _block_name(self, block: int) -> str:
        name = self._names.get(block)
        if name is None:
            try:
                name = short_id(self._string(self._q(block + self.legacy_off) + self.name_off))
            except Exception:
                name = ""
            self._names[block] = name
        return name

    # --- storage layouts ----------------------------------------------------------------
    def _layout_for_bits(self, bits: int) -> Layout:
        if bits == 0:
            return Layout(0, 0, self.words_off, 1)
        per_word = 32 // bits
        words = -(-4096 // per_word)
        palette = (self.words_off + words * 4 + 7) & ~7
        return Layout(bits, words, palette, 1 << bits)

    def _layout(self, storage: int, vtable: int) -> Layout | None:
        if vtable in self._layouts:
            return self._layouts[vtable]
        layout = None
        if vtable in self.known_layouts:
            layout = self._layout_for_bits(self.known_layouts[vtable])
        else:   # unknown storage class (e.g. after an update): find the bit width whose palette is valid
            for bits in (0, 1, 2, 3, 4, 5, 6, 8):
                cand = self._layout_for_bits(bits)
                if self._palette(storage, cand):
                    layout = cand
                    log.info("Learned storage vtable +0x%X = %d bits/block", vtable - self.base, bits)
                    break
        self._layouts[vtable] = layout
        return layout

    def _palette(self, storage: int, layout: Layout) -> list[int] | None:
        try:
            if layout.bits == 0:
                entries = [self._q(storage + layout.palette)]
            else:
                size = self._q(storage + layout.palette + layout.capacity * 8)
                if not 1 <= size <= layout.capacity:
                    return None
                entries = list(struct.unpack(f"<{size}Q", self.pm.read_bytes(storage + layout.palette, size * 8)))
            for e in entries:
                if e not in self._good_blocks:
                    if self._q(e) != self.block_vt:
                        return None
                    self._good_blocks.add(e)
            return entries
        except Exception:
            pass
        return None

    # --- chunks --------------------------------------------------------------------------
    def _full_scan(self) -> None:
        self._last_full_scan = time.monotonic()
        self.status = "locating chunk data (first time, ~30 s)..."
        started = time.monotonic()
        hits = sorted(h - self.member_off for h in find_qword(self.pm, self.member_vt, self._stop.is_set))
        pools = []
        for addr in hits:      # group into runs of slots at the pool stride
            if pools:
                first, count = pools[-1]
                gap = addr - (first + (count - 1) * self.stride)
                if gap > 0 and gap % self.stride == 0 and gap <= self.stride * POOL_MERGE_GAP:
                    pools[-1] = (first, count + gap // self.stride)
                    continue
            pools.append((addr, 1))
        self._pools = pools
        log.info("Chunk pools: %d chunks in %d runs (%.1fs)", len(hits), len(pools), time.monotonic() - started)

    def _discover(self) -> None:
        """Walk the pool slots (a few small reads each) and remember every chunk of our dimension.

        Chunks never move once allocated, so between discoveries the known addresses are reused.
        """
        self._last_discovery = time.monotonic()
        found: dict[tuple[int, int], int] = {}
        grown = []
        dimension = self.dimension
        head_lo = min(self.pos_off, self.dim_off if self.dim_off is not None else self.pos_off)
        head_len = max(self.pos_off + 8, (self.dim_off or 0) + 8) - head_lo
        for n, (first, count) in enumerate(self._pools):
            start = first - DISCOVERY_MARGIN * self.stride
            lo = hi = None
            for i in range(count + 2 * DISCOVERY_MARGIN):
                addr = start + i * self.stride
                try:
                    if self._q(addr + self.member_off) != self.member_vt:
                        continue
                    head = self.pm.read_bytes(addr + head_lo, head_len)
                except Exception:
                    continue
                lo = i if lo is None else lo
                hi = i
                if dimension and self.dim_off is not None:
                    if struct.unpack_from("<Q", head, self.dim_off - head_lo)[0] != dimension:
                        continue        # another dimension (or the integrated server's copy)
                found.setdefault(struct.unpack_from("<ii", head, self.pos_off - head_lo), addr)
            if lo is not None:
                grown.append((start + lo * self.stride, hi - lo + 1))
            if n % 8 == 0:
                time.sleep(0)            # let the overlay thread run
        if grown:
            self._pools = grown
        self._known = found
        self._known_dimension = dimension

    def _still_valid(self, addr: int, pos: tuple[int, int]) -> bool:
        try:
            if self._q(addr + self.member_off) != self.member_vt:
                return False
            return struct.unpack("<ii", self.pm.read_bytes(addr + self.pos_off, 8)) == pos
        except Exception:
            return False

    # --- sections -------------------------------------------------------------------------
    def _scan_chunk(self, chunk: int, pos: tuple[int, int], wanted: frozenset[str], out: list[BlockHit]) -> None:
        begin, end = struct.unpack("<QQ", self.pm.read_bytes(chunk + self.sections_off, 16))
        count = (end - begin) // self.section_size
        if not 0 < count <= 64:
            return
        min_y = -64 if count == 24 else 0          # overworld has 24 sections from y -64
        raw = self.pm.read_bytes(begin, count * self.section_size)
        for s in range(count):
            for layer_off in self.layer_offs:
                storage = struct.unpack_from("<Q", raw, s * self.section_size + layer_off)[0]
                if storage:
                    self._scan_storage(storage, pos[0] * 16, min_y + s * 16, pos[1] * 16, wanted, out)
                if len(out) >= MAX_HITS:
                    return

    def _scan_storage(self, storage, bx, by, bz, wanted, out) -> None:
        try:
            layout = self._layout(storage, self._q(storage))
        except Exception:
            return
        if layout is None:
            return
        palette = self._palette(storage, layout)
        if not palette:
            return
        targets = {i: name for i, b in enumerate(palette) if (name := self._block_name(b)) in wanted}
        if not targets:
            return
        if layout.bits == 0:     # whole section is one block type
            name = targets[0]
            out.extend(BlockHit(bx + i // 256, by + i % 16, bz + (i // 16) % 16, name) for i in range(4096))
            return
        raw = self.pm.read_bytes(storage + self.words_off, layout.words * 4)
        self._seen.add(storage)
        key = (raw, tuple(palette), wanted, bx, by, bz)
        cached = self._decoded.get(storage)
        if cached is not None and cached[0] == key:
            out.extend(cached[1])          # unchanged since last cycle: no decoding
            return
        start = len(out)
        self._decode(raw, layout, targets, bx, by, bz, out)
        self._decoded[storage] = (key, out[start:])

    def _decode(self, raw, layout, targets, bx, by, bz, out) -> None:
        words = struct.unpack(f"<{layout.words}I", raw)
        bits, per_word, mask = layout.bits, 32 // layout.bits, (1 << layout.bits) - 1
        index = 0
        for w in words:
            if w:   # skip words that are all palette index 0 (often air) unless 0 is a target
                for j in range(per_word):
                    v = (w >> (j * bits)) & mask
                    if v in targets:
                        i = index + j
                        if i < 4096:
                            out.append(BlockHit(bx + (i >> 8), by + (i & 15), bz + ((i >> 4) & 15), targets[v]))
            elif 0 in targets:
                for j in range(per_word):
                    i = index + j
                    if i < 4096:
                        out.append(BlockHit(bx + (i >> 8), by + (i & 15), bz + ((i >> 4) & 15), targets[0]))
            index += per_word

    # --- loop -------------------------------------------------------------------------------
    def _cycle(self) -> None:
        wanted, center = self.wanted, self.center
        if not wanted or center is None:
            self.hits, self.status = [], ""
            return
        if not self._pools and time.monotonic() - self._last_full_scan > FULL_SCAN_COOLDOWN:
            self._full_scan()
            self._last_discovery = -DISCOVERY_SECONDS
        here = (math.floor(center[0] / 16), math.floor(center[2] / 16))
        if (time.monotonic() - self._last_discovery > DISCOVERY_SECONDS
                or self.dimension != self._known_dimension or here not in self._known):
            if time.monotonic() - self._last_discovery > 2.0:     # never more than every 2 s
                self._discover()
        chunks = self._known
        if here not in chunks:
            self._missing += 1
            if self._missing >= MISSING_CYCLES_FOR_RESCAN and time.monotonic() - self._last_full_scan > FULL_SCAN_COOLDOWN:
                self._missing = 0
                self._full_scan()
                self._discover()
                chunks = self._known
        else:
            self._missing = 0
        radius = min(MAX_RADIUS_CHUNKS, math.ceil(self.radius_blocks / 16) + 1)
        out: list[BlockHit] = []
        scanned = 0
        for (cx, cz), chunk in list(chunks.items()):
            if abs(cx - here[0]) > radius or abs(cz - here[1]) > radius:
                continue
            if not self._still_valid(chunk, (cx, cz)):
                chunks.pop((cx, cz), None)      # unloaded; the next discovery picks up replacements
                continue
            scanned += 1
            try:
                self._scan_chunk(chunk, (cx, cz), wanted, out)
            except Exception:
                continue
            if scanned % 8 == 0:
                time.sleep(0)                   # let the overlay thread run
            if len(out) >= MAX_HITS:
                break
        self.hits = out
        if len(self._decoded) > len(self._seen) * 2 + 1000:
            self._decoded = {k: v for k, v in self._decoded.items() if k in self._seen}
        self._seen = set()
        if len(self._good_blocks) > 100_000:
            self._good_blocks.clear()
        if not chunks:
            self.status = "no chunk data found yet"
        elif len(out) >= MAX_HITS:
            self.status = f"too many matches, showing the first {MAX_HITS}"
        else:
            self.status = ""
        log.debug("Block scan: %d chunks in range, %d hits", scanned, len(out))

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self._cycle()
            except Exception:
                log.exception("Block scan cycle failed")
                self.status = "scan error (see log)"
            self._stop.wait(max(0.1, CYCLE_SECONDS - (time.monotonic() - started)))
