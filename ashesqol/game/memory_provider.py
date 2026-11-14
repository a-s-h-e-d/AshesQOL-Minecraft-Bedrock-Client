"""Reads the local player and nearby actors straight from Minecraft's memory (read-only).

How it finds things (offsets in data/offsets.json, details in docs/recon-*.md):
- LocalPlayer: static pointer chain, checked against the player's vtable.
- Actor list: the client registry's EnTT storage of Actor*, reached by pointer chain or,
  if every chain breaks, by a one-off background scan for the storage's vtable. Either way it's
  accepted only if its table contains our local player (single-player also has a server copy).
"""
import logging
import math
import struct
import threading
import time
from dataclasses import dataclass

from ..core.memory import find_qword_in, find_qwords, find_qwords_in_segment_heads, probe_aligned
from ..core.offsets import Offsets
from ..core.process import GameProcess
from .math3d import Vec3
from .block_scanner import BlockScanner
from .camera_rotation import CameraRotation
from .providers import DataProvider
from .state import Entity, GameState, LocalPlayer

log = logging.getLogger(__name__)

MAX_ACTORS = 4096
SCAN_BACKOFF = (60.0, 600.0)  # full fallback scans: first retry after 60 s, doubling up to 10 min
RESOLVE_INTERVAL = 1.0    # seconds between attempts to find the player / storage
NOT_ACTOR_SECONDS = 2.0   # skip table entries that weren't actors for this long
TICK_SECONDS = 0.05       # 20 game ticks per second
MAX_INTERP_DISTANCE = 8.0 # blocks; bigger jumps are teleports, not movement


def _angle_delta(a: float, b: float) -> float:
    """Shortest signed turn from angle a to angle b, in degrees (handles the +-180 wrap)."""
    return (b - a + 180.0) % 360.0 - 180.0


def _finite(*values) -> bool:
    return all(math.isfinite(v) and abs(v) < 3e7 for v in values)


@dataclass(frozen=True)
class PlayerBody:
    player_addr: int
    pos: Vec3        # StateVector pos (eye height for players)
    min: Vec3        # hitbox
    max: Vec3

    def moved(self, d: Vec3) -> "PlayerBody":
        return PlayerBody(self.player_addr, self.pos + d, self.min + d, self.max + d)


class TickClock:
    """Estimates how far we are into the game's current 20 TPS tick (0..1).

    The game only moves things on ticks, so whenever any position changes between two polls a tick
    happened in between. Those observations are noisy by up to one frame, so they're blended into a
    steady 50 ms rhythm instead of being trusted outright.
    """

    def __init__(self):
        self.last_tick: float | None = None
        self._signature = None
        self._last_poll: float | None = None

    def update(self, signature, now: float) -> float:
        since_poll = 0.0 if self._last_poll is None else now - self._last_poll
        self._last_poll = now
        if signature != self._signature:
            self._signature = signature
            observed = now - since_poll / 2       # the tick happened somewhere since the last poll
            if self.last_tick is None:
                self.last_tick = observed
            else:
                ticks = max(1, round((observed - self.last_tick) / TICK_SECONDS))
                predicted = self.last_tick + ticks * TICK_SECONDS
                error = observed - predicted
                self.last_tick = predicted + 0.3 * error if abs(error) < TICK_SECONDS / 2 else observed
        if self.last_tick is None:
            return 1.0
        return min(1.0, max(0.0, (now - self.last_tick) / TICK_SECONDS))


def pretty_type(type_id: str) -> str:
    """'minecraft:zombie_villager_v2' -> 'Zombie Villager'."""
    short = type_id.split(":", 1)[-1]
    if short.endswith("_v2"):
        short = short[:-3]
    return short.replace("_", " ").title()


class MemoryProvider(DataProvider):
    key = "memory"
    label = "Memory (Minecraft)"

    def __init__(self, process: GameProcess, offsets: Offsets):
        self.process = process
        self.offsets = offsets
        self.player_addr: int | None = None
        self.storage_addr: int | None = None
        self._player_cooldown = 0.0
        self._storage_cooldown = 0.0
        self._types: dict[tuple[int, int], str] = {}   # (actor, vtable) -> type id
        self._scan_thread: threading.Thread | None = None
        self._scan_hits: int | None = None     # actor storage found by the background search
        self._last_scan = -SCAN_BACKOFF[1]
        self._scan_wait = 0.0          # grows after each fruitless full scan
        self.interpolate = True
        self.ignore_version = False      # 'Try anyway' on unsupported game versions
        self.clock = TickClock()
        self._prev_rotation = (0.0, 0.0)
        self._tick_rotation = (0.0, 0.0)
        self.block_range = 64.0
        self._blocks: BlockScanner | None = None
        self._block_cache_key = None
        self._block_cache: list = []
        self._camera: CameraRotation | None = None
        self._not_actor: dict[int, float] = {}   # table entries that aren't actors -> retry time
        self.dimension_ptr: int | None = None
        self._dimension_names: dict[int, str] = {}

    # --- low-level reads -------------------------------------------------------
    @property
    def _pm(self):
        return self.process.pm

    def _q(self, addr: int) -> int:
        return self._pm.read_ulonglong(addr)

    def _floats(self, addr: int, count: int) -> tuple[float, ...]:
        return struct.unpack(f"<{count}f", self._pm.read_bytes(addr, count * 4))

    def _in_module(self, value: int) -> bool:
        base = self.process.base_address
        return base <= value < base + self.process.module_size

    def _vtables(self, section: str) -> set[int]:
        return {self.process.base_address + v for v in self.offsets.vtables(section)}

    def _has_vtable(self, addr: int, section: str) -> bool:
        try:
            return self._q(addr) in self._vtables(section)
        except Exception:
            return False

    def _follow(self, chain: list[int]) -> int | None:
        try:
            ptr = self._q(self.process.base_address + chain[0])
            for off in chain[1:]:
                ptr = self._q(ptr + off)
            return ptr
        except Exception:
            return None

    # --- local player ----------------------------------------------------------
    def _resolve_player(self) -> tuple[int | None, int | None]:
        """(player, actor storage if it was found on the way)."""
        for i, chain in enumerate(self.offsets.chains("local_player")):
            addr = self._follow(chain)
            if addr and self._has_vtable(addr, "local_player"):
                log.info("Local player found via chain #%d at 0x%X", i, addr)
                return self._found(addr, None)

        # Fast path (single-player): fixed offset inside an aligned heap segment. A few hundred tiny reads.
        arena = self.offsets.arena("local_player")
        if arena:
            for target in self._vtables("local_player"):
                hits = [h for h in probe_aligned(self._pm, arena[0], arena[1], target) if self._readable_actor(h)]
                if hits:
                    log.info("Local player found in heap segment at 0x%X", hits[0])
                    return self._found(hits[0], None)

        # Background search (Realms etc.): the local player is entry 0 of the client actor storage.
        found = self._search_result()
        if found:
            player, storage = found
            log.info("Local player 0x%X found through actor storage 0x%X", player, storage)
            return self._found(player, storage)
        return None, None

    def _found(self, player: int, storage: int | None) -> tuple[int, int | None]:
        self._scan_wait = 0.0       # reset the search backoff
        return player, storage

    def _player_from_storage(self, storage: int) -> int | None:
        """Entry 0 of a client actor storage, if it's a live local player."""
        if not self._has_vtable(storage, "actor_storage"):
            return None
        try:
            actors = self._storage_actors(storage)
        except Exception:
            return None
        if actors and self._has_vtable(actors[0], "local_player") and self._readable_actor(actors[0]):
            return actors[0]
        return None

    def _readable_actor(self, addr: int) -> bool:
        """Its component pointers lead to sane position data (filters out stale freed copies)."""
        try:
            state_ptr = self._q(addr + self.offsets.get("actor", "state_vector"))
            return _finite(*self._floats(state_ptr, 3))
        except Exception:
            return False

    def _dimension_name(self, player: int) -> str:
        """'overworld' / 'nether' / 'the_end' from the player's Dimension object (cached per pointer)."""
        self.dimension_ptr = None
        if "dimension" not in self.offsets.data.get("actor", {}):
            return "overworld"
        try:
            dim = self._q(player + self.offsets.get("actor", "dimension"))
        except Exception:
            return "overworld"
        self.dimension_ptr = dim
        if dim not in self._dimension_names:
            name = ""
            try:
                at = dim + self.offsets.get("dimension", "name")
                size, cap = struct.unpack("<QQ", self._pm.read_bytes(at + 0x10, 16))
                if size <= 32:
                    raw = self._pm.read_bytes(at, size) if cap < 16 else self._pm.read_bytes(self._q(at), size)
                    name = raw.decode(errors="replace").lower()
            except Exception:
                pass
            self._dimension_names[dim] = {"overworld": "overworld", "nether": "nether", "theend": "the_end"}.get(name, "overworld")
        return self._dimension_names[dim]

    def _read_motion(self, state_ptr: int) -> Vec3:
        """posPrev - pos: how far back the entity was at the previous game tick."""
        o = self.offsets
        px, py, pz = self._floats(state_ptr + o.get("state_vector", "pos"), 3)
        qx, qy, qz = self._floats(state_ptr + o.get("state_vector", "pos_prev"), 3)
        back = Vec3(qx - px, qy - py, qz - pz)
        if not _finite(back.x, back.y, back.z) or back.length() > MAX_INTERP_DISTANCE:
            return Vec3(0.0, 0.0, 0.0)   # teleport/respawn: don't smear across the map
        return back

    def _read_player(self, addr: int) -> tuple[LocalPlayer, Vec3]:
        o = self.offsets
        aabb_ptr = self._q(addr + o.get("actor", "aabb"))
        rot_ptr = self._q(addr + o.get("actor", "rotation"))
        state_ptr = self._q(addr + o.get("actor", "state_vector"))

        px, _eye_y, pz = self._floats(state_ptr + o.get("state_vector", "pos"), 3)
        feet_y = self._floats(aabb_ptr + o.get("aabb", "min"), 3)[1]
        _width, height = self._floats(aabb_ptr + o.get("aabb", "width"), 2)
        pitch, yaw, prev_pitch, prev_yaw = self._floats(rot_ptr + o.get("rotation", "pitch"), 4)
        if not _finite(prev_pitch, prev_yaw):
            prev_pitch, prev_yaw = pitch, yaw
        self._prev_rotation = (prev_pitch, prev_yaw)
        self._tick_rotation = (pitch, yaw)          # tick-rate values: used to detect game ticks
        # Prefer the per-frame camera rotation; the component above only updates once per tick.
        if "camera_rotation" in self.offsets.data:
            if self._camera is None or self._camera.pm is not self._pm:
                self._camera = CameraRotation(self._pm, self.process.base_address, self.offsets.data)
            live = self._camera.read(pitch, yaw, rot_ptr + o.get("rotation", "pitch"))
            if live is not None:
                pitch, yaw = live

        # Standing eye height is 1.62 of a 1.8 hitbox; scale so sneaking/swimming stays right.
        eye_height = 1.62 * (height / 1.8) if height > 0 else 1.62
        player = LocalPlayer(pos=Vec3(px, feet_y, pz), yaw=yaw, pitch=pitch, eye_height=eye_height,
                             dimension=self._dimension_name(addr))
        return player, self._read_motion(state_ptr)

    # --- writing the local player's position (Freecam) -----------------------------
    def read_player_body(self) -> "PlayerBody | None":
        """Raw position + hitbox of the local player (pos is at eye height for players)."""
        if self.player_addr is None:
            return None
        try:
            o = self.offsets
            state_ptr = self._q(self.player_addr + o.get("actor", "state_vector"))
            aabb_ptr = self._q(self.player_addr + o.get("actor", "aabb"))
            pos = Vec3(*self._floats(state_ptr + o.get("state_vector", "pos"), 3))
            mn = Vec3(*self._floats(aabb_ptr + o.get("aabb", "min"), 3))
            mx = Vec3(*self._floats(aabb_ptr + o.get("aabb", "max"), 3))
        except Exception:
            return None
        if not _finite(pos.x, pos.y, pos.z, mn.x, mn.y, mn.z, mx.x, mx.y, mx.z):
            return None
        return PlayerBody(self.player_addr, pos, mn, mx)

    def write_player_body(self, body: "PlayerBody") -> bool:
        """Move the client-side player: pos = posPrev = body.pos, zero velocity, hitbox to match.

        Writing pos and the hitbox together stops the next physics tick from snapping it back.
        """
        if body.player_addr != self.player_addr:
            return False
        try:
            o = self.offsets
            state_ptr = self._q(self.player_addr + o.get("actor", "state_vector"))
            aabb_ptr = self._q(self.player_addr + o.get("actor", "aabb"))
            p = body.pos
            state = struct.pack("<9f", p.x, p.y, p.z, p.x, p.y, p.z, 0.0, 0.0, 0.0)
            self._pm.write_bytes(state_ptr + o.get("state_vector", "pos"), state, len(state))
            aabb = struct.pack("<6f", body.min.x, body.min.y, body.min.z, body.max.x, body.max.y, body.max.z)
            self._pm.write_bytes(aabb_ptr + o.get("aabb", "min"), aabb, len(aabb))
            return True
        except Exception:
            log.exception("Writing player position failed")
            return False

    # --- actor storage -----------------------------------------------------------
    def _storage_count(self, storage: int) -> int:
        o = self.offsets
        begin = self._q(storage + o.get("actor_storage", "packed_begin"))
        end = self._q(storage + o.get("actor_storage", "packed_end"))
        return (end - begin) // 4

    def _storage_actors(self, storage: int) -> list[int]:
        """Every Actor* in the storage, in table order."""
        o = self.offsets
        count = self._storage_count(storage)
        if not 0 < count <= MAX_ACTORS:
            return []
        page_size = int(self.offsets.data["actor_storage"]["page_size"])
        pages = self._q(storage + o.get("actor_storage", "pages"))
        actors = []
        for page_index in range(math.ceil(count / page_size)):
            page = self._q(pages + page_index * 8)
            n = min(page_size, count - page_index * page_size)
            actors.extend(struct.unpack(f"<{n}Q", self._pm.read_bytes(page, n * 8)))
        return actors

    def _is_client_storage(self, storage: int, player: int) -> bool:
        if not self._has_vtable(storage, "actor_storage"):
            return False
        try:
            return player in self._storage_actors(storage)
        except Exception:
            return False

    def _resolve_storage(self, player: int) -> int | None:
        for i, chain in enumerate(self.offsets.chains("actor_storage")):
            addr = self._follow(chain)
            if addr and self._is_client_storage(addr, player):
                log.info("Actor storage found via chain #%d at 0x%X", i, addr)
                return addr

        # Fast path: it lives near the start of the player's heap segment.
        arena = self.offsets.arena("local_player")
        if arena:
            segment = player & ~(arena[0] - 1)
            window = self.offsets.get("actor_storage", "arena_window")
            target = self.process.base_address + self.offsets.vtable("actor_storage")
            for addr in find_qword_in(self._pm, segment, window, target):
                if self._is_client_storage(addr, player):
                    log.info("Actor storage found in player segment at 0x%X", addr)
                    return addr

        found = self._search_result()
        if found and found[0] == player:
            return found[1]
        return None

    # --- background search (when the shortcuts miss) ------------------------------------
    def _search_result(self) -> tuple[int, int] | None:
        """(player, storage) from a finished background search, consumed once.
        Starts a search if none is running and the backoff allows it."""
        result, self._scan_hits = self._scan_hits, None
        if result is not None:
            player = self._player_from_storage(result)   # re-check: memory may have moved on
            if player is not None:
                return player, result
        if self._scan_thread is None and time.monotonic() - self._last_scan > self._scan_wait:
            self._start_scan()
        return None

    def _start_scan(self) -> None:
        self._last_scan = time.monotonic()
        self._scan_wait = min(SCAN_BACKOFF[1], max(SCAN_BACKOFF[0], self._scan_wait * 2))
        pm = self._pm
        target = self.process.base_address + self.offsets.vtable("actor_storage")
        align = (self.offsets.arena("local_player") or (0x1000000, 0))[0]
        window = self.offsets.get("actor_storage", "segment_window")
        stop = lambda: self.process.pm is not pm   # noqa: E731 - game closed / re-attached
        log.info("Shortcut lookup missed; searching memory in the background "
                 "(next automatic search in %.0f s if this finds nothing)", self._scan_wait)

        def pick(candidates):
            for storage in candidates:
                if self._player_from_storage(storage) is not None:
                    return storage
            return None

        def work():
            started = time.monotonic()
            storage = None
            try:
                # Phase 1 (~1-2 s): the storage sits near the start of a 16 MB heap segment.
                storage = pick(find_qwords_in_segment_heads(pm, [target], align, window, stop)[target])
                if storage is None and not stop():
                    log.info("Segment search missed; full memory scan (~30 s)...")
                    storage = pick(find_qwords(pm, [target], stop)[target])
            except Exception:
                log.exception("Background search failed")
            log.info("Background search %s in %.1fs",
                     f"found actor storage 0x{storage:X}" if storage else "found nothing",
                     time.monotonic() - started)
            self._scan_hits = storage
            self._scan_thread = None

        self._scan_thread = threading.Thread(target=work, name="memory-scan", daemon=True)
        self._scan_thread.start()

    # --- actors ----------------------------------------------------------------------
    def _type_of(self, actor: int, vtable: int, blob: bytes) -> str:
        key = (actor, vtable)
        cached = self._types.get(key)
        if cached is not None:
            return cached
        off = self.offsets.get("actor", "type_name")
        size, cap = struct.unpack_from("<QQ", blob, off + 0x10)
        if size > 200:
            return "unknown"
        raw = blob[off:off + size] if cap < 16 else self._pm.read_bytes(struct.unpack_from("<Q", blob, off)[0], size)
        type_id = raw.decode(errors="replace").split(".", 1)[0]  # player ids carry '.persona-...' suffixes
        if len(self._types) > 10_000:
            self._types.clear()
        self._types[key] = type_id
        return type_id

    def _read_actor(self, actor: int) -> tuple[Entity, Vec3] | None:
        o = self.offsets
        aabb_off = o.get("actor", "aabb")
        now = time.monotonic()
        if self._not_actor.get(actor, 0.0) > now:
            return None                      # recently seen as "not an actor": skip the reads
        try:
            blob = self._pm.read_bytes(actor, aabb_off + 8)
            vtable = struct.unpack_from("<Q", blob, 0)[0]
            if not self._in_module(vtable):
                if len(self._not_actor) > 50_000:
                    self._not_actor.clear()
                self._not_actor[actor] = now + NOT_ACTOR_SECONDS
                return None
            type_id = self._type_of(actor, vtable, blob)
            aabb_ptr = struct.unpack_from("<Q", blob, aabb_off)[0]
            state_ptr = struct.unpack_from("<Q", blob, o.get("actor", "state_vector"))[0]
            mnx, mny, mnz, mxx, _mxy, mxz, width, height = self._floats(aabb_ptr, 8)
            back = self._read_motion(state_ptr)
        except Exception:
            return None
        if not _finite(mnx, mny, mnz, mxx, mxz, width, height) or not (0 < height < 50):
            return None
        entity = Entity(uid=actor, type_id=type_id, name=pretty_type(type_id),
                        pos=Vec3((mnx + mxx) / 2, mny, (mnz + mxz) / 2), width=width, height=height)
        return entity, back

    def _read_entities(self, player: int) -> list[tuple[Entity, Vec3]]:
        if not self.offsets.has_entities:
            return []
        if self.storage_addr is None or not self._has_vtable(self.storage_addr, "actor_storage"):
            self.storage_addr = None
            if self._storage_cooldown > 0:
                return []
            self._storage_cooldown = RESOLVE_INTERVAL
            self.storage_addr = self._resolve_storage(player)
            if self.storage_addr is None:
                return []
        try:
            actors = self._storage_actors(self.storage_addr)
        except Exception:
            self.storage_addr = None
            return []
        if player not in actors:  # world changed under us
            self.storage_addr = None
            return []
        entities = []
        for actor in actors:
            if actor and actor != player:
                read = self._read_actor(actor)
                if read is not None:
                    entities.append(read)
        return entities

    # --- per frame ---------------------------------------------------------------------
    def poll(self, dt: float) -> GameState:
        if self.process.pid is None:
            return GameState.invalid("Minecraft is not running", self.key)
        if self._pm is None:
            return GameState.invalid(f"Not attached: {self.process.attach_error or 'attaching...'}", self.key)
        if not self.offsets.ready:
            return GameState.invalid("Attached - offsets not set (memory recon step)", self.key)
        if not self.ignore_version and not self.offsets.supports(self.process.version):
            # Different game build: the offsets almost certainly moved. Don't run memory searches that
            # can't succeed; say what's wrong instead.
            return GameState.invalid(
                f"Minecraft {self.process.version} isn't supported yet "
                f"(offsets are for {self.offsets.exe_version})", self.key)

        self._player_cooldown -= dt
        self._storage_cooldown -= dt

        # Re-validate every frame; the player object is recreated on world/dimension change.
        if self.player_addr is None or not self._has_vtable(self.player_addr, "local_player"):
            self.player_addr = None
            self.storage_addr = None
            if self._player_cooldown > 0:
                return self._not_found()
            self._player_cooldown = RESOLVE_INTERVAL
            self.player_addr, self.storage_addr = self._resolve_player()
            if self.player_addr is None:
                return self._not_found()

        try:
            player, player_back = self._read_player(self.player_addr)
        except Exception as e:
            self.player_addr = None
            return GameState.invalid(f"Read failed: {e}", self.key)
        read = self._read_entities(self.player_addr)

        # Smooth movement like the game does: draw at posPrev + (pos - posPrev) * alpha,
        # where alpha is how far we are into the current 50 ms tick.
        if self.interpolate:
            signature = (player.pos.x, player.pos.y, player.pos.z, *self._tick_rotation,
                         *(c for e, _ in read for c in (e.pos.x, e.pos.y, e.pos.z)))
            back_fraction = 1.0 - self.clock.update(signature, time.perf_counter())
            player.pos = player.pos + player_back * back_fraction
            # Rotation is NOT blended: the game's camera turns every frame and is *ahead* of this
            # once-per-tick value, so blending toward prevYaw only adds lag (tested 2026-11-13).
            for e, back in read:
                e.pos = e.pos + back * back_fraction
        blocks, status = self._update_block_scanner(player)
        notices = self._entity_notices()
        if status:
            notices.append(("blocks", f"BlockESP: {status}"))
        return GameState(valid=True, source=self.key, player=player, entities=[e for e, _ in read],
                         blocks=blocks, block_status=status, notices=notices)

    # --- on-screen notices while data is still being located --------------------------
    def _not_found(self) -> GameState:
        state = GameState.invalid("Not in a world (player not found)", self.key)
        if self._scan_thread is not None:
            state.notices = [("entities", "ESP: locating player data in memory (on servers this can take ~40 s)...")]
        return state

    def _entity_notices(self) -> list[tuple[str, str]]:
        notices = []
        if self.storage_addr is None and self._scan_thread is not None:
            notices.append(("entities", "ESP: locating the entity list..."))
        cam = self._camera
        if cam is not None and cam.entry_addr is None and cam._thread is not None:
            notices.append(("entities", "ESP: finding the camera (~30 s; boxes may trail when turning until then)..."))
        return notices

    # --- blocks (background scanner) ---------------------------------------------------
    def _update_block_scanner(self, player: LocalPlayer):
        if not self.wanted_blocks or "chunk" not in self.offsets.data:
            if self._blocks is not None:
                self._blocks.wanted = frozenset()   # idle, but keep the learned chunk pools
            return [], ""
        if self._blocks is None or self._blocks.pm is not self._pm or not self._blocks.alive:
            if self._blocks is not None:
                self._blocks.stop()
            self._blocks = BlockScanner(self._pm, self.process.base_address, self.offsets.data)
        scanner = self._blocks
        scanner.wanted = self.wanted_blocks
        scanner.center = (player.pos.x, player.pos.y, player.pos.z)
        scanner.radius_blocks = self.block_range
        scanner.dimension = self.dimension_ptr
        # The scanner replaces its list about once a second; only re-filter when it (or the selection) changes.
        key = (id(scanner.hits), self.wanted_blocks)
        if key != self._block_cache_key:
            self._block_cache_key = key
            self._block_cache = [b for b in scanner.hits if b.block in self.wanted_blocks]
        return self._block_cache, scanner.status

    def reset(self) -> None:
        """Forget everything found so far (e.g. after the offsets were updated)."""
        self.shutdown()
        self._blocks = None
        self._camera = None
        self.player_addr = self.storage_addr = None
        self._types.clear()
        self._not_actor.clear()
        self._dimension_names.clear()
        self._scan_hits = None
        self._scan_wait = 0.0
        self._last_scan = -SCAN_BACKOFF[1]

    def shutdown(self) -> None:
        if self._blocks is not None:
            self._blocks.stop()
