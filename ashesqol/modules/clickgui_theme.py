from PyQt6.QtGui import QColor

from ..ui.render import rainbow_at
from .base import Module
from .settings import BoolSetting, ColorSetting, SliderSetting


class ClickGuiTheme(Module):
    """Appearance of the in-game click GUI. Settings only: nothing to turn on or off."""

    name = "ClickGUI"
    category = "Client"
    description = "Colors and font of this click GUI."
    toggleable = False

    def setup(self) -> None:
        self.add(ColorSetting("accent", "Accent color", (255, 120, 40, 255)))
        self.add(BoolSetting("rainbow", "RGB accent (rainbow)", False))
        self.add(SliderSetting("rainbow_speed", "RGB speed", 1.0, 0.1, 5.0, 0.1))
        self.add(ColorSetting("panel", "Panel color", (18, 18, 24, 235)))
        self.add(ColorSetting("text", "Text color", (232, 232, 236, 255)))
        self.add(ColorSetting("header_text", "Header text color", (20, 20, 24, 255)))
        self.add(SliderSetting("dim", "Background dimming", 90, 0, 220, 5))
        self.add(BoolSetting("mc_font", "Minecraft font", False))

    def accent(self, y: float = 0.0, height: float = 1080.0) -> QColor:
        """Accent at a screen height; in RGB mode the colors roll down the screen."""
        if self.val("rainbow"):
            return rainbow_at(y, height, self.val("rainbow_speed"))
        return self.settings["accent"].qcolor
