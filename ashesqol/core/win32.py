"""Thin ctypes wrappers over the Win32 calls we need (windows, focus, keys)."""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

_EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

# Fallback title for the old UWP build, whose window belongs to ApplicationFrameHost.exe.
GAME_WINDOW_TITLE = "Minecraft"


def window_title(hwnd) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def find_game_window(pid: int):
    """Largest visible top-level window owned by pid, else a window titled exactly 'Minecraft'."""
    best, best_area, fallback = None, -1, None   # -1: a minimized window (0x0 client area) still counts

    @_EnumWindowsProc
    def callback(hwnd, _):
        nonlocal best, best_area, fallback
        if not user32.IsWindowVisible(hwnd):
            return True
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            rect = client_rect_on_screen(hwnd)
            area = rect[2] * rect[3] if rect else 0
            if area > best_area:
                best, best_area = hwnd, area
        elif fallback is None and window_title(hwnd) == GAME_WINDOW_TITLE:
            fallback = hwnd
        return True

    user32.EnumWindows(callback, 0)
    return best or fallback


def client_rect_on_screen(hwnd):
    """(x, y, w, h) of the window's client area in physical screen pixels."""
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    origin = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    return origin.x, origin.y, rect.right, rect.bottom


def is_window(hwnd) -> bool:
    return bool(hwnd) and bool(user32.IsWindow(hwnd))


def is_minimized(hwnd) -> bool:
    return bool(user32.IsIconic(hwnd))


def foreground_window():
    return user32.GetForegroundWindow()


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]


def force_foreground(hwnd) -> None:
    """Give hwnd keyboard focus even when another app (the game) owns the foreground.

    Windows refuses SetForegroundWindow from background processes; temporarily attaching our
    input queue to the current foreground thread is the standard way around that.
    """
    if not hwnd:
        return
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return
    fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    our_thread = _kernel32.GetCurrentThreadId()
    attached = bool(fg_thread) and fg_thread != our_thread and user32.AttachThreadInput(our_thread, fg_thread, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(our_thread, fg_thread, False)


def make_click_through(hwnd) -> None:
    """Ensure clicks pass through the window and it never steals focus."""
    style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)


# --- Keyboard -----------------------------------------------------------------

VK = {
    "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23,
    "PAGEUP": 0x21, "PAGEDOWN": 0x22, "RSHIFT": 0xA1, "RCONTROL": 0xA3,
    "LALT": 0xA4, "RALT": 0xA5, "CAPSLOCK": 0x14, "TAB": 0x09,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "SPACE": 0x20, "LSHIFT": 0xA0, "LCONTROL": 0xA2,
}
VK.update({f"NUMPAD{i}": 0x60 + i for i in range(10)})
VK.update({chr(c): c for c in range(ord("A"), ord("Z") + 1)})
VK.update({chr(c): c for c in range(ord("0"), ord("9") + 1)})
VK.update({f"F{i}": 0x6F + i for i in range(1, 25)})


def key_down(name: str) -> bool:
    vk = VK.get(name)
    return vk is not None and bool(user32.GetAsyncKeyState(vk) & 0x8000)


class KeyWatcher:
    """Edge-detects global key presses by polling (no hooks needed)."""

    def __init__(self):
        self._down: set[str] = set()

    def poll(self, names) -> set[str]:
        now = {n for n in names if key_down(n)}
        pressed = now - self._down
        self._down = now
        return pressed
