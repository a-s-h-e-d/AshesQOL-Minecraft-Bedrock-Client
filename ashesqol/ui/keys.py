"""Map Qt key events to the key names used by core.win32.VK (shared by every keybind picker)."""
from PyQt6.QtCore import Qt

from ..core.win32 import VK

_SPECIAL_KEYS = {
    Qt.Key.Key_Insert: "INSERT", Qt.Key.Key_Delete: "DELETE", Qt.Key.Key_Home: "HOME",
    Qt.Key.Key_End: "END", Qt.Key.Key_PageUp: "PAGEUP", Qt.Key.Key_PageDown: "PAGEDOWN",
    Qt.Key.Key_CapsLock: "CAPSLOCK", Qt.Key.Key_Tab: "TAB", Qt.Key.Key_Space: "SPACE",
    Qt.Key.Key_Up: "UP", Qt.Key.Key_Down: "DOWN", Qt.Key.Key_Left: "LEFT", Qt.Key.Key_Right: "RIGHT",
}
# Qt reports Shift/Ctrl/Alt without a side; the Windows scan code tells left from right.
_SCAN_SIDES = {
    Qt.Key.Key_Shift: {0x2A: "LSHIFT", 0x36: "RSHIFT"},
    Qt.Key.Key_Control: {0x1D: "LCONTROL", 0x11D: "RCONTROL"},
    Qt.Key.Key_Alt: {0x38: "LALT", 0x138: "RALT"},
}
_NUMPAD = {getattr(Qt.Key, f"Key_{i}").value: f"NUMPAD{i}" for i in range(10)}


def key_name(event) -> str | None:
    """Key name for a QKeyEvent, or None if the key isn't supported as a bind."""
    key = event.key()
    for qt_key, sides in _SCAN_SIDES.items():
        if key == qt_key.value:
            return sides.get(event.nativeScanCode(), next(iter(sides.values())))
    if event.modifiers() & Qt.KeyboardModifier.KeypadModifier and key in _NUMPAD:
        return _NUMPAD[key]
    for qt_key, name in _SPECIAL_KEYS.items():
        if key == qt_key.value:
            return name
    if Qt.Key.Key_F1.value <= key <= Qt.Key.Key_F24.value:
        return f"F{key - Qt.Key.Key_F1.value + 1}"
    if 0 <= key < 0x110000:
        name = chr(key).upper()
        if name in VK:
            return name
    return None


def pretty(name: str | None) -> str:
    """'RSHIFT' -> 'Right Shift' for display."""
    if not name:
        return "none"
    for prefix, side in (("L", "Left"), ("R", "Right")):
        for mod, label in (("SHIFT", "Shift"), ("CONTROL", "Ctrl"), ("ALT", "Alt")):
            if name == prefix + mod:
                return f"{side} {label}"
    return name.title() if len(name) > 1 else name
