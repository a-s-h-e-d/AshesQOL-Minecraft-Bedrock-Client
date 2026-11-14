"""App-wide settings persisted to config/settings.json."""
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "settings.json"

DEFAULTS = {
    "source": "mock",              # "mock" (demo data) or "memory" (read from Minecraft)
    "only_when_focused": True,     # hide the overlay when Minecraft isn't the active window
    "preview_background": True,    # dim the preview area when no game window is found
    "fov": 70.0,                   # must match the in-game FOV until we read it from memory
    "menu_key": "INSERT",          # shows/hides the control window
    "toggle_key": "END",           # master switch: turns all of AshesQOL off/on
    "clickgui_key": "RSHIFT",      # in-game click GUI (Left Shift would clash with sneaking)
    "show_control_on_start": True, # False: start with only the click GUI / hotkeys
    "max_fps": 0,                  # overlay redraw rate; 0 = match the monitor's refresh rate
    "interpolate": True,           # smooth movement between the game's 20 ticks/s
    "ignore_version_check": False, # True: try the current offsets even on a different game build
    "modules": {},
}


class Config:
    def __init__(self, data: dict):
        self.data = {**DEFAULTS, **data}

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    @classmethod
    def load(cls) -> "Config":
        if CONFIG_PATH.exists():
            try:
                return cls(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
            except (OSError, ValueError) as e:
                log.warning("Could not read %s (%s); using defaults", CONFIG_PATH, e)
        return cls({})

    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        tmp.replace(CONFIG_PATH)
