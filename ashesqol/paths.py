"""Where AshesQOL's files live, both from source and as a PyInstaller executable.

From source:      everything stays in the repo (config/, ashesqol/data/offsets.json).
As AshesQOL.exe:  the exe unpacks to a temporary folder on every launch, so anything that must
                  survive (settings, updated offsets, the log) is kept next to the exe instead.
"""
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))

# Read-only files that ship with AshesQOL (inside the exe when frozen).
PACKAGE_DIR = (Path(sys._MEIPASS) / "ashesqol") if FROZEN else Path(__file__).resolve().parent

# Writable folder: next to the exe, or the repo root when running from source.
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else PACKAGE_DIR.parent

CONFIG_PATH = APP_DIR / "config" / "settings.json"
BUNDLED_OFFSETS = PACKAGE_DIR / "data" / "offsets.json"
# Offsets written by the automatic update. From source that's the repo file itself.
USER_OFFSETS = APP_DIR / "offsets.json" if FROZEN else BUNDLED_OFFSETS
LOG_PATH = APP_DIR / "ashesqol.log"
ICON_PATH = PACKAGE_DIR / "data" / "icon.ico"
