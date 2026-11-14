"""Finds the running Minecraft process/window and (optionally) opens it for memory reads."""
import ctypes
import logging
from ctypes import wintypes

import pymem
import pymem.process

from . import win32

log = logging.getLogger(__name__)

PROCESS_NAME = "Minecraft.Windows.exe"

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD)]
_version = ctypes.WinDLL("version", use_last_error=True)


class _FixedFileInfo(ctypes.Structure):
    _fields_ = [(name, wintypes.DWORD) for name in (
        "signature", "struc_version", "file_ms", "file_ls", "product_ms", "product_ls",
        "flags_mask", "flags", "os", "type", "subtype", "date_ms", "date_ls")]


def exe_path_of(handle) -> str | None:
    buf = ctypes.create_unicode_buffer(1024)
    size = wintypes.DWORD(len(buf))
    if _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
        return buf.value
    return None


def file_version(path: str) -> str | None:
    """'1.26.63.1' from the executable's version resource."""
    size = _version.GetFileVersionInfoSizeW(path, None)
    if not size:
        return None
    data = ctypes.create_string_buffer(size)
    if not _version.GetFileVersionInfoW(path, 0, size, data):
        return None
    ptr, length = ctypes.c_void_p(), wintypes.UINT()
    if not _version.VerQueryValueW(data, "\\", ctypes.byref(ptr), ctypes.byref(length)) or not ptr.value:
        return None
    info = ctypes.cast(ptr, ctypes.POINTER(_FixedFileInfo)).contents
    return f"{info.file_ms >> 16}.{info.file_ms & 0xFFFF}.{info.file_ls >> 16}.{info.file_ls & 0xFFFF}"


def find_pid(name: str = PROCESS_NAME):
    for entry in pymem.process.list_processes():
        if entry.szExeFile.decode(errors="ignore").lower() == name.lower():
            return entry.th32ProcessID
    return None


class GameProcess:
    def __init__(self):
        self.pid = None
        self.hwnd = None
        self.pm: pymem.Pymem | None = None
        self.base_address = None
        self.module_size = None
        self.attach_error: str | None = None
        self.exe_path: str | None = None
        self.version: str | None = None     # e.g. "1.26.63.1"

    def _reset(self):
        if self.pm is not None:
            try:
                self.pm.close_process()
            except Exception:  # process may already be gone
                pass
        self.pid = self.hwnd = self.pm = None
        self.base_address = self.module_size = None
        self.attach_error = None
        self.exe_path = self.version = None

    def refresh(self, want_memory: bool) -> None:
        """Called about once a second: track the process, its window, and attach if asked."""
        pid = find_pid()
        if pid != self.pid:
            self._reset()
            self.pid = pid
            if pid:
                log.info("Found %s (pid %d)", PROCESS_NAME, pid)
        if self.pid is None:
            return
        if not win32.is_window(self.hwnd):
            self.hwnd = win32.find_game_window(self.pid)
        if want_memory and self.pm is None and self.attach_error is None:
            self._attach()

    def retry_attach(self) -> None:
        self.attach_error = None

    def _attach(self) -> None:
        try:
            pm = pymem.Pymem()
            pm.open_process_from_id(self.pid)
            module = pymem.process.module_from_name(pm.process_handle, PROCESS_NAME)
            if module is None:
                raise RuntimeError(f"module {PROCESS_NAME} not found in process")
            self.base_address = module.lpBaseOfDll
            self.module_size = module.SizeOfImage
            self.exe_path = exe_path_of(pm.process_handle)
            self.version = file_version(self.exe_path) if self.exe_path else None
            self.pm = pm
            log.info("Attached: Minecraft %s, base=0x%X size=0x%X", self.version or "(unknown version)",
                     self.base_address, self.module_size)
        except Exception as e:
            self.attach_error = str(e) or type(e).__name__
            log.warning("Attach failed: %s", self.attach_error)
