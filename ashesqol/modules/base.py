"""Module base class. Subclass it, declare settings in setup(), draw in on_render()."""
from dataclasses import dataclass

from .settings import Setting


@dataclass
class TickContext:
    state: object                 # game.state.GameState
    dt: float
    memory: object | None         # MemoryProvider when reading the real game, else None
    game_focused: bool            # Minecraft is the foreground window


class Module:
    name = "Module"
    description = ""
    category = "Render"
    enabled_by_default = False
    persist_enabled = True        # False: always starts disabled (e.g. modules that write game memory)
    toggleable = True             # False: settings-only module (e.g. ClickGUI appearance); never "enabled"

    def __init__(self):
        self.enabled = self.enabled_by_default
        self.keybind: str | None = None
        self.settings: dict[str, Setting] = {}
        self.setup()

    # --- declaration -------------------------------------------------------
    def setup(self) -> None:
        """Declare settings with self.add(...)."""

    def add(self, setting: Setting) -> Setting:
        self.settings[setting.key] = setting
        return setting

    def val(self, key: str):
        return self.settings[key].value

    # --- lifecycle ---------------------------------------------------------
    def set_enabled(self, enabled: bool) -> None:
        if not self.toggleable:
            enabled = False
        if enabled == self.enabled:
            return
        self.enabled = enabled
        self.on_enable() if enabled else self.on_disable()

    def toggle(self) -> None:
        self.set_enabled(not self.enabled)

    def on_enable(self) -> None: ...
    def on_disable(self) -> None: ...

    def on_tick(self, ctx: TickContext) -> None:
        """Logic every frame (automation goes here). Runs before rendering."""

    def on_shutdown(self) -> None:
        """App is closing: undo any changes made to the game."""

    def wanted_blocks(self) -> set[str]:
        """Block ids (short form) this module needs the data source to find. Only asked while enabled."""
        return set()

    def block_range(self) -> float:
        """How far (blocks) the data source should look for wanted_blocks()."""
        return 0.0

    def on_render(self, ctx) -> None:
        """Draw on the overlay. ctx is a ui.render.RenderContext."""

    # --- persistence -------------------------------------------------------
    def to_json(self) -> dict:
        return {
            "enabled": self.enabled,
            "keybind": self.keybind,
            "settings": {k: s.to_json() for k, s in self.settings.items()},
        }

    def load_json(self, data: dict) -> None:
        if self.persist_enabled and self.toggleable:
            self.enabled = bool(data.get("enabled", self.enabled))
        self.keybind = data.get("keybind") or None
        for key, raw in data.get("settings", {}).items():
            if key in self.settings:
                self.settings[key].load(raw)
