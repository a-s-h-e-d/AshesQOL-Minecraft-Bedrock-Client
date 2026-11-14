"""Automatic offset update after a Minecraft update ("self-heal").

Game updates recompile the game, which moves the code addresses (vtables) that AshesQOL uses to
recognise objects. Where data sits *inside* those objects (field offsets) usually doesn't change in
a hotfix, so every vtable can be found again from anchors that survive updates:

  1. Player names     - find the text "minecraft:player..." in memory.
  2. Player objects   - actors whose type-name field (actor + type_name) points at that text.
  3. Entity lists     - EnTT storages whose page 0 starts with one of those players. The same
                        search follows the player's rotation pointer to the camera storage type.
  4. Chunk            - the chunk at the player's position (ChunkPos + section vector + dimension).
  5. Blocks           - that chunk's sections give the Block class and the storage layouts.
  6. Validation       - a fresh MemoryProvider must find the player with the new values before
                        anything is saved.

If any step fails (for example because a field offset moved too) nothing is changed and the error
says which step failed; that update needs a manual pass (see docs/).
"""
import copy
import json
import logging
import math
import struct
import threading
import time
from collections import Counter

from ..core.memory import find_bytes, find_qwords_in_set
from ..core.offsets import OFFSETS_PATH, Offsets

log = logging.getLogger(__name__)

STEPS = 6
VALIDATE_SECONDS = 90


class RediscoveryError(Exception):
    """A step failed; the message is shown to the user."""


def _h(v) -> int:
    return int(v, 16) if isinstance(v, str) else int(v)


class Rediscovery:
    def __init__(self, process, offsets: Offsets):
        self.process = process
        self.old = offsets
        self.status = "starting..."
        self.done = False
        self.ok = False
        self.error = ""
        self.result: dict | None = None
        self.backup_path = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="offset-update", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # --- plumbing -------------------------------------------------------------------------
    def _step(self, n: int, text: str) -> None:
        self.status = f"step {n}/{STEPS}: {text}"
        log.info("Offset update %s", self.status)

    def _check_stop(self) -> None:
        if self._stop.is_set() or self.process.pm is not self.pm:
            raise RediscoveryError("cancelled (Minecraft closed or AshesQOL stopped)")

    def _q(self, addr: int) -> int:
        return self.pm.read_ulonglong(addr)

    def _floats(self, addr: int, n: int):
        return struct.unpack(f"<{n}f", self.pm.read_bytes(addr, n * 4))

    def _string(self, addr: int) -> str:
        size, cap = struct.unpack("<QQ", self.pm.read_bytes(addr + 0x10, 16))
        if size > 200:
            return ""
        raw = self.pm.read_bytes(addr, size) if cap < 16 else self.pm.read_bytes(self._q(addr), size)
        return raw.decode(errors="replace")

    def _safe_q(self, addr: int):
        try:
            return self._q(addr)
        except Exception:
            return None

    def _in_module(self, v: int) -> bool:
        return self.base <= v < self.base + self.process.module_size

    def _run(self) -> None:
        self.pm = self.process.pm
        self.base = self.process.base_address
        try:
            if self.pm is None:
                raise RediscoveryError("not attached to Minecraft")
            new = self._discover()
            self._step(6, "checking the new values...")
            self._validate(new)
            self._save(new)
            self.result, self.ok = new, True
            self.status = "done"
            log.info("Offsets updated for Minecraft %s", self.process.version)
        except RediscoveryError as e:
            self.error = str(e)
            log.warning("Offset update failed: %s", e)
        except Exception as e:      # unexpected: still never leave a half-written file behind
            self.error = f"unexpected error: {e}"
            log.exception("Offset update crashed")
        finally:
            self.done = True

    # --- steps -----------------------------------------------------------------------------
    def _discover(self) -> dict:
        d = copy.deepcopy(self.old.data)
        actor = {k: _h(v) for k, v in d["actor"].items() if not k.startswith("_")}
        store = {k: _h(d["actor_storage"][k]) for k in ("packed_begin", "packed_end", "pages")}
        stop = lambda: self._stop.is_set() or self.process.pm is not self.pm   # noqa: E731

        # 1. player names ------------------------------------------------------------------
        self._step(1, "searching memory for player names (you must be in a world)...")
        names = set(find_bytes(self.pm, b"minecraft:player.", stop))
        self._check_stop()
        if not names:
            raise RediscoveryError("no player found in memory. Join a world (single-player or a Realm) and try again")

        # 2. player objects ----------------------------------------------------------------
        self._step(2, f"finding player objects ({len(names)} name copies)...")
        players = []
        for holder, _ in find_qwords_in_set(self.pm, names, stop):
            obj = holder - actor["type_name"]
            if self._looks_like_actor(obj, actor):
                players.append(obj)
        self._check_stop()
        if not players:
            raise RediscoveryError("found player names but no player objects: the actor layout changed (manual update needed)")
        log.info("Offset update: %d player-like actors", len(players))

        # 3. entity lists (and the camera storage type) -------------------------------------
        self._step(3, "finding the entity list and camera...")
        rotations = {}
        for p in players:
            try:
                rotations[self._q(p + actor["rotation"])] = p
            except Exception:
                pass
        # EnTT storage: storage+pages -> page vector slot -> page -> entries.
        #   actor list:  page entries are Actor*, so  player <- page[0] <- slot <- storage
        #   rotations:   components live in the page,  rotation ptr == page[0]  <- slot <- storage
        actor_pages = {a for a, _ in find_qwords_in_set(self.pm, set(players), stop)}   # places holding a player*
        self._check_stop()
        slots = {a for a, _ in find_qwords_in_set(self.pm, actor_pages | set(rotations), stop)}
        self._check_stop()
        storages = []
        for holder, slot in find_qwords_in_set(self.pm, slots, stop):                  # storage + pages
            info = self._storage(holder - store["pages"], slot, store)
            if info:
                storages.append(info)
        self._check_stop()
        actor_lists = [(st, vt, self._q(page)) for st, vt, page in storages
                       if page in actor_pages and self._safe_q(page) in players]
        if not actor_lists:
            raise RediscoveryError("no entity list starts with a player: the storage layout changed (manual update needed)")
        storage_vt = Counter(vt for _, vt, _ in actor_lists).most_common(1)[0][0]
        local_players = [first for _, vt, first in actor_lists if vt == storage_vt]
        player_vts = sorted({self._q(p) for p in local_players})
        local = local_players[0]
        camera_vts = [vt for st, vt, page in storages if page in rotations and rotations[page] in local_players]
        if not camera_vts:
            raise RediscoveryError("couldn't find the rotation storage: the layout changed (manual update needed)")
        camera_vt = Counter(camera_vts).most_common(1)[0][0]

        # 4. the chunk the player stands in ---------------------------------------------------
        self._step(4, "finding the chunk you're standing in...")
        c = {k: _h(v) for k, v in d["chunk"].items() if not k.startswith("_") and k != "member_vtable"}
        px, _, pz = self._floats(self._q(local + actor["state_vector"]), 3)
        here = (math.floor(px / 16), math.floor(pz / 16))
        dim = self._q(local + actor["dimension"])
        chunk = None
        for hit in find_bytes(self.pm, struct.pack("<ii", *here), stop, align=4):
            cand = hit - c["pos"]
            if self._looks_like_chunk(cand, c, dim):
                chunk = cand
                break
        self._check_stop()
        if chunk is None:
            raise RediscoveryError("couldn't find the chunk you're standing in: the chunk layout changed (manual update needed)")
        member_vt = self._q(chunk + c["member_offset"])
        if not self._in_module(member_vt):
            raise RediscoveryError("chunk found but its member object moved (manual update needed)")

        # 5. block class and storage layouts ------------------------------------------------------
        self._step(5, "reading block data in that chunk...")
        block_vt, layouts = self._blocks(chunk, c, d)
        if block_vt is None:
            raise RediscoveryError("couldn't read the block palettes: the block storage changed (manual update needed)")

        # assemble ---------------------------------------------------------------------------------
        rva = lambda v: f"0x{v - self.base:X}"   # noqa: E731
        d["local_player"]["vtable"] = [rva(v) for v in player_vts]
        d["local_player"]["chains"] = []
        seg = local & ~(_h(d["local_player"]["arena"]["align"]) - 1)
        d["local_player"]["arena"]["offset"] = f"0x{local - seg:X}"
        d["actor_storage"]["vtable"] = rva(storage_vt)
        d["actor_storage"]["chains"] = []
        d["camera_rotation"]["storage_vtable"] = rva(camera_vt)
        d["chunk"]["member_vtable"] = rva(member_vt)
        d["block"]["vtable"] = rva(block_vt)
        d["block_storage"]["layouts"] = {rva(vt): bits for vt, bits in sorted(layouts.items())}
        d["exe_version"] = self.process.version
        d["game_version"] = ".".join(self.process.version.split(".")[:3])
        return d

    def _looks_like_actor(self, obj: int, actor: dict) -> bool:
        try:
            if not self._in_module(self._q(obj)):
                return False
            pos = self._floats(self._q(obj + actor["state_vector"]), 3)
            mn = self._floats(self._q(obj + actor["aabb"]), 8)
            rot = self._floats(self._q(obj + actor["rotation"]), 2)
        except Exception:
            return False
        width, height = mn[6], mn[7]
        return (all(math.isfinite(v) and abs(v) < 3e7 for v in pos + rot)
                and 0.1 < width < 5 and 0.1 < height < 5 and abs(rot[0]) <= 90.01)

    def _storage(self, st: int, slot: int, store: dict):
        """(storage, vtable, page 0 address) if st looks like an EnTT storage whose page vector starts at slot."""
        try:
            vt = self._q(st)
            if not self._in_module(vt) or self._q(st + store["pages"]) != slot:
                return None
            begin, end = self._q(st + store["packed_begin"]), self._q(st + store["packed_end"])
            if not 0 < (end - begin) // 4 <= 100_000:
                return None
            return st, vt, self._q(slot)
        except Exception:
            return None

    def _looks_like_chunk(self, cand: int, c: dict, dim: int) -> bool:
        try:
            begin, end = struct.unpack("<QQ", self.pm.read_bytes(cand + c["sections"], 16))
            count = (end - begin) // c["section_size"] if end > begin else 0
            return ((end - begin) % c["section_size"] == 0 and count in (8, 16, 24)
                    and self._q(cand + c["dimension"]) == dim)
        except Exception:
            return False

    def _blocks(self, chunk: int, c: dict, d: dict):
        words = _h(d["block_storage"]["words"])
        legacy, name = _h(d["block"]["legacy"]), _h(d["block"]["name"])
        begin, end = struct.unpack("<QQ", self.pm.read_bytes(chunk + c["sections"], 16))
        storages = []
        for s in range((end - begin) // c["section_size"]):
            for layer in ("layer0", "layer1"):
                st = self._q(begin + s * c["section_size"] + c[layer])
                if st:
                    storages.append(st)
        block_vt, layouts = None, {}
        for st in storages:
            vt = self._q(st)
            if vt in layouts:
                continue
            for bits in (0, 1, 2, 3, 4, 5, 6, 8):
                entries = self._palette(st, bits, words)
                if not entries:
                    continue
                vts = {self._safe_q(e) for e in entries}     # a wrong bit-width guess gives garbage pointers
                if len(vts) != 1 or None in vts or not self._in_module(next(iter(vts))):
                    continue
                try:
                    names_ok = all(self._string(self._q(e + legacy) + name).startswith("minecraft:") for e in entries)
                except Exception:
                    names_ok = False
                if names_ok and (block_vt is None or block_vt == next(iter(vts))):
                    block_vt = next(iter(vts))
                    layouts[vt] = bits
                    break
        return block_vt, layouts

    def _palette(self, st: int, bits: int, words_off: int):
        try:
            if bits == 0:
                return [self._q(st + words_off)]
            per_word = 32 // bits
            pal = (st + words_off + (-(-4096 // per_word)) * 4 + 7) & ~7
            cap = 1 << bits
            size = self._q(pal + cap * 8)
            if not 1 <= size <= cap:
                return None
            return list(struct.unpack(f"<{size}Q", self.pm.read_bytes(pal, size * 8)))
        except Exception:
            return None

    # --- validation and saving ------------------------------------------------------------------------
    def _validate(self, data: dict) -> None:
        from .memory_provider import MemoryProvider      # local import: avoid a cycle
        trial = copy.deepcopy(data)
        trial.pop("camera_rotation", None)       # already verified in step 3; skip its 30 s search here
        provider = MemoryProvider(self.process, Offsets(trial))
        deadline = time.monotonic() + VALIDATE_SECONDS
        state = provider.poll(1.0)
        while not state.valid and time.monotonic() < deadline:
            self._check_stop()
            time.sleep(0.5)
            state = provider.poll(0.5)
        provider.shutdown()
        if not state.valid:
            raise RediscoveryError(f"the new values didn't work ({state.reason})")
        p = state.player.pos
        if not all(math.isfinite(v) for v in (p.x, p.y, p.z)):
            raise RediscoveryError("the new values gave an invalid position")
        if provider.dimension_ptr is None:
            raise RediscoveryError("the new values didn't find your dimension")

    def _save(self, data: dict) -> None:
        old_version = self.old.exe_version or "unknown"
        backup = OFFSETS_PATH.with_name(f"offsets.{old_version}.json")
        if not backup.exists():
            backup.write_text(json.dumps(self.old.data, indent=2) + "\n", encoding="utf-8")
        tmp = OFFSETS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tmp.replace(OFFSETS_PATH)
        self.backup_path = backup
