"""Loads Minecraft's own font (Mojangles.ttf) from the user's installed game.

AshesQOL doesn't ship the font: it's read from <game>/data/fonts/Mojangles.ttf. The game folder
comes from the running process's executable path, or from the installed app package.
"""
import ctypes
import logging
import subprocess
from ctypes import wintypes
from pathlib import Path

from PyQt6.QtGui import QFont, QFontDatabase

log = logging.getLogger(__name__)

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD)]
_RELATIVE = Path("data") / "fonts" / "Mojangles.ttf"
_family: str | None = None
_tried = False


def _exe_dir(process) -> Path | None:
    pm = getattr(process, "pm", None)
    if pm is None:
        return None
    buf = ctypes.create_unicode_buffer(1024)
    size = wintypes.DWORD(len(buf))
    if _kernel32.QueryFullProcessImageNameW(pm.process_handle, 0, buf, ctypes.byref(size)):
        return Path(buf.value).parent
    return None


def _package_dir() -> Path | None:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-AppxPackage -Name '*MinecraftUWP*' | Select-Object -First 1).InstallLocation"],
            capture_output=True, text=True, timeout=15, creationflags=0x08000000)   # CREATE_NO_WINDOW
        path = out.stdout.strip()
        return Path(path) if path else None
    except Exception:
        return None


def minecraft_family(process=None) -> str | None:
    """Qt font family name for Minecraft's font, or None if it can't be found (cached)."""
    global _family, _tried
    if _family or _tried:
        return _family
    for folder in (_exe_dir(process), _package_dir()):
        if folder is None:
            continue
        path = folder / _RELATIVE
        if path.exists():
            font_id = QFontDatabase.addApplicationFont(str(path))
            families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
            if families:
                _family = families[0]
                log.info("Loaded Minecraft font '%s' from %s", _family, path)
                break
    _tried = True       # only look once; a missing font shouldn't cost time every frame
    if _family is None:
        log.warning("Minecraft font not found; using the default font")
    return _family


def pixel_font(family: str, scale: int = 2) -> QFont:
    """Mojangles is a pixel font on an 8 px grid: only exact multiples with no smoothing stay crisp
    (in-between sizes blur letters, e.g. 'c' turns into 'o')."""
    font = QFont(family)
    font.setPixelSize(8 * scale)
    font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def overlay_font(use_minecraft: bool, process=None, size: float = 10.0) -> QFont:
    family = minecraft_family(process) if use_minecraft else None
    if family:
        return pixel_font(family)
    font = QFont("Segoe UI")
    font.setPointSizeF(size)
    font.setWeight(QFont.Weight.DemiBold)
    return font
