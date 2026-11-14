"""Low-level keyboard hook that can hide chosen keys from the game (used by Freecam for WASD).

While installed it tracks the up/down state of the watched keys itself (blocked keys never
reach GetAsyncKeyState). Only key-DOWN events are swallowed: releases always pass through, so
the game can never get stuck thinking a key is held.
The hook runs on the thread that installs it, which must pump messages (the Qt main thread does).
"""
import ctypes
import logging
from ctypes import wintypes

log = logging.getLogger(__name__)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105

_LRESULT = ctypes.c_ssize_t
_HookProc = ctypes.WINFUNCTYPE(_LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HookProc, wintypes.HINSTANCE, wintypes.DWORD]
_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
_user32.CallNextHookEx.restype = _LRESULT
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class KeyBlocker:
    def __init__(self, vk_codes, should_block=lambda: True):
        self.vk_codes = set(vk_codes)
        self.should_block = should_block   # checked per key event (e.g. "is the game focused?")
        self.down: set[int] = set()
        self._hook = None
        self._proc = _HookProc(self._callback)  # keep a reference or ctypes frees it

    @property
    def installed(self) -> bool:
        return self._hook is not None

    def install(self) -> bool:
        if self._hook:
            return True
        self.down.clear()
        self._hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, _kernel32.GetModuleHandleW(None), 0)
        if not self._hook:
            log.error("SetWindowsHookExW failed (error %d)", ctypes.get_last_error())
        return bool(self._hook)

    def uninstall(self) -> None:
        if self._hook:
            _user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        self.down.clear()

    def is_down(self, vk: int) -> bool:
        return vk in self.down

    def _callback(self, code, wparam, lparam):
        try:
            if code == 0:
                kb = ctypes.cast(lparam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                if kb.vkCode in self.vk_codes:
                    if wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        if self.should_block():
                            self.down.add(kb.vkCode)
                            return 1          # swallow: the game never sees this press
                    elif wparam in (WM_KEYUP, WM_SYSKEYUP):
                        self.down.discard(kb.vkCode)   # always let releases through
        except Exception:
            log.exception("keyboard hook callback failed")
        return _user32.CallNextHookEx(None, code, wparam, lparam)
