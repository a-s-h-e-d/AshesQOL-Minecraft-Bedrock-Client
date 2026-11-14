"""Read-only process memory helpers: region enumeration and value search."""
import ctypes
import time
from ctypes import wintypes

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)


class _MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_uint64), ("AllocationBase", ctypes.c_uint64),
                ("AllocationProtect", wintypes.DWORD), ("PartitionId", wintypes.WORD),
                ("RegionSize", ctypes.c_uint64), ("State", wintypes.DWORD),
                ("Protect", wintypes.DWORD), ("Type", wintypes.DWORD)]


_k32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_uint64, ctypes.POINTER(_MBI), ctypes.c_size_t]
_k32.VirtualQueryEx.restype = ctypes.c_size_t

MEM_COMMIT = 0x1000
_WRITABLE = {0x04, 0x08, 0x40, 0x80}  # RW, WRITECOPY, RWX, WXCOPY
_CHUNK = 4 << 20     # small reads so background scans never hold the GIL for long


def writable_regions(handle, max_region: int = 1 << 30):
    """Yield (base, size) for committed, writable regions (heap, stacks, module .data)."""
    addr, mbi = 0, _MBI()
    while addr < 0x7FFFFFFFFFFF and _k32.VirtualQueryEx(handle, addr, ctypes.byref(mbi), ctypes.sizeof(mbi)):
        base, size = mbi.BaseAddress, mbi.RegionSize
        if mbi.State == MEM_COMMIT and (mbi.Protect & 0xFF) in _WRITABLE and size <= max_region:
            yield base, size
        addr = base + size


def _find_in(buf: bytes, needle: bytes, base: int, out: list[int]) -> None:
    i = buf.find(needle)
    while i != -1:
        if i % 8 == 0:
            out.append(base + i)
        i = buf.find(needle, i + 1)


def find_qwords(pm, values, should_stop=lambda: False) -> dict[int, list[int]]:
    """Full scan (slow, ~15-30 s): addresses of every 8-byte-aligned qword equal to each value."""
    needles = {v: v.to_bytes(8, "little") for v in values}
    found = {v: [] for v in values}
    for base, size in writable_regions(pm.process_handle):
        for off in range(0, size, _CHUNK):
            if should_stop():
                return found
            try:
                buf = pm.read_bytes(base + off, min(_CHUNK, size - off))
            except Exception:
                continue
            for v, needle in needles.items():
                _find_in(buf, needle, base + off, found[v])
            time.sleep(0)    # yield to the overlay thread between chunks
    return found


def find_qwords_in_segment_heads(pm, values, align: int, window: int,
                                 should_stop=lambda: False) -> dict[int, list[int]]:
    """Like find_qwords, but only the first `window` bytes of every align-aligned segment (~1-2 s)."""
    needles = {v: v.to_bytes(8, "little") for v in values}
    found = {v: [] for v in values}
    for base, size in writable_regions(pm.process_handle):
        seg = base - base % align
        while seg < base + size:
            if should_stop():
                return found
            lo, hi = max(base, seg), min(base + size, seg + window)
            if lo < hi:
                try:
                    buf = pm.read_bytes(lo, hi - lo)
                    for v, needle in needles.items():
                        _find_in(buf, needle, lo, found[v])
                except Exception:
                    pass
                time.sleep(0)
            seg += align
    return found


def find_bytes(pm, needle: bytes, should_stop=lambda: False, align: int = 1) -> list[int]:
    """Every address where `needle` occurs (optionally only at multiples of `align`)."""
    found: list[int] = []
    overlap = len(needle) - 1
    for base, size in writable_regions(pm.process_handle):
        for off in range(0, size, _CHUNK):
            if should_stop():
                return found
            try:
                buf = pm.read_bytes(base + off, min(_CHUNK + overlap, size - off))
            except Exception:
                continue
            i = buf.find(needle)
            while i != -1 and i < _CHUNK:
                if (base + off + i) % align == 0:
                    found.append(base + off + i)
                i = buf.find(needle, i + 1)
            time.sleep(0)
    return found


def find_qwords_in_set(pm, values, should_stop=lambda: False) -> list[tuple[int, int]]:
    """(address, value) for every 8-byte-aligned qword whose value is in `values` (needs numpy)."""
    import numpy as np                     # only needed for this (offset rediscovery)
    if not values:
        return []
    targets = np.array(sorted(values), dtype=np.uint64)
    found: list[tuple[int, int]] = []
    for base, size in writable_regions(pm.process_handle):
        for off in range(0, size, _CHUNK):
            if should_stop():
                return found
            try:
                buf = pm.read_bytes(base + off, min(_CHUNK, size - off))
            except Exception:
                continue
            a = np.frombuffer(buf[: len(buf) // 8 * 8], dtype=np.uint64)
            for i in np.nonzero(np.isin(a, targets))[0]:
                found.append((base + off + int(i) * 8, int(a[i])))
            time.sleep(0)
    return found


def find_qword(pm, value: int, should_stop=lambda: False) -> list[int]:
    return find_qwords(pm, [value], should_stop)[value]


def find_qword_in(pm, start: int, size: int, value: int) -> list[int]:
    """Scan only [start, start+size) for value; unreadable pages are skipped."""
    needle = value.to_bytes(8, "little")
    found: list[int] = []
    for base, rsize in writable_regions(pm.process_handle):
        lo, hi = max(base, start), min(base + rsize, start + size)
        if lo >= hi:
            continue
        try:
            _find_in(pm.read_bytes(lo, hi - lo), needle, lo, found)
        except Exception:
            pass
    return found


def probe_aligned(pm, align: int, offset: int, value: int) -> list[int]:
    """Check the qword at (every align-aligned address + offset) inside writable memory. Fast."""
    hits = []
    for base, size in writable_regions(pm.process_handle):
        a = -(-(base - offset) // align) * align      # first aligned a with a + offset >= base
        while a + offset + 8 <= base + size:
            try:
                if pm.read_ulonglong(a + offset) == value:
                    hits.append(a + offset)
            except Exception:
                pass
            a += align
    return hits
