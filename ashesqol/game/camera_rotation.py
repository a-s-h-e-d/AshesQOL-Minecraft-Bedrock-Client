"""Per-frame camera rotation (read-only).

The player's ActorRotationComponent (what the rest of the code reads) only changes once per game
tick, while the game turns the view every frame. A second rotation storage (EnTT, same
(pitch, yaw, prevPitch, prevYaw) layout, in another registry) holds the per-frame value for the
local player in entry 0. Its storage vtable is shared with other component types, so it is found
by elimination: a valid storage with that vtable, which is not the client's tick-rate one, whose
entry 0 matches the player's rotation. Found once per world by a background scan (~30 s).
"""
import logging
import math
import struct
import threading
import time

from ..core.memory import find_qword

log = logging.getLogger(__name__)

RETRY_SECONDS = (60.0, 600.0)  # retry after 60 s, doubling up to 10 min while nothing is found
MAX_DISAGREEMENT = 45.0       # degrees; beyond this the per-frame value is considered stale


def _angle_gap(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


class CameraRotation:
    def __init__(self, pm, base: int, offsets: dict):
        self.pm = pm
        self.vtable = base + int(offsets["camera_rotation"]["storage_vtable"], 16)
        self.pages_off = int(offsets["actor_storage"]["pages"], 16)
        self.begin_off = int(offsets["actor_storage"]["packed_begin"], 16)
        self.end_off = int(offsets["actor_storage"]["packed_end"], 16)
        self.entry_addr: int | None = None     # address of (pitch, yaw) for the local player
        self._exclude: int | None = None        # the client's tick-rate rotation page entry
        self._candidates: list[int] | None = None
        self._thread: threading.Thread | None = None
        self._last_search = -RETRY_SECONDS[1]
        self._retry = 0.0
        self._bad_frames = 0

    def _entry0(self, storage: int) -> int | None:
        try:
            if self.pm.read_ulonglong(storage) != self.vtable:
                return None
            begin = self.pm.read_ulonglong(storage + self.begin_off)
            end = self.pm.read_ulonglong(storage + self.end_off)
            if not 0 < (end - begin) // 4 <= 100_000:
                return None
            return self.pm.read_ulonglong(self.pm.read_ulonglong(storage + self.pages_off))
        except Exception:
            return None

    def _start_search(self) -> None:
        self._last_search = time.monotonic()
        self._retry = min(RETRY_SECONDS[1], max(RETRY_SECONDS[0], self._retry * 2))
        pm, target = self.pm, self.vtable

        def work():
            started = time.monotonic()
            try:
                hits = find_qword(pm, target)
            except Exception:
                log.exception("Camera rotation search failed")
                hits = []
            self._candidates = hits
            self._thread = None
            log.info("Camera rotation search: %d storages with the vtable (%.1fs)", len(hits), time.monotonic() - started)

        self._thread = threading.Thread(target=work, name="camera-scan", daemon=True)
        self._thread.start()

    def _pick(self, tick_pitch: float, tick_yaw: float) -> None:
        cands, self._candidates = self._candidates, None
        for storage in cands or []:
            entry = self._entry0(storage)
            if entry is None or entry == self._exclude:
                continue
            try:
                pitch, yaw = struct.unpack("<2f", self.pm.read_bytes(entry, 8))
            except Exception:
                continue
            if math.isfinite(pitch) and math.isfinite(yaw) and abs(pitch) <= 90 \
                    and _angle_gap(yaw, tick_yaw) < 10 and abs(pitch - tick_pitch) < 10:
                self.entry_addr = entry
                self._retry = 0.0
                log.info("Per-frame camera rotation found (storage 0x%X)", storage)
                return

    def read(self, tick_pitch: float, tick_yaw: float, tick_entry: int) -> tuple[float, float] | None:
        """Per-frame (pitch, yaw), or None to keep using the tick values."""
        self._exclude = tick_entry
        if self.entry_addr is None:
            if self._candidates is not None:
                self._pick(tick_pitch, tick_yaw)
            elif self._thread is None and time.monotonic() - self._last_search > self._retry:
                self._start_search()
            if self.entry_addr is None:
                return None
        try:
            pitch, yaw = struct.unpack("<2f", self.pm.read_bytes(self.entry_addr, 8))
        except Exception:
            pitch = yaw = float("nan")
        if not (math.isfinite(pitch) and math.isfinite(yaw)) or abs(pitch) > 90 \
                or _angle_gap(yaw, tick_yaw) > MAX_DISAGREEMENT or abs(pitch - tick_pitch) > MAX_DISAGREEMENT:
            self._bad_frames += 1
            if self._bad_frames > 30:          # stale (world change, entity reordered): find it again
                log.info("Per-frame camera rotation lost; searching again")
                self.entry_addr, self._bad_frames = None, 0
            return None
        self._bad_frames = 0
        return pitch, yaw
