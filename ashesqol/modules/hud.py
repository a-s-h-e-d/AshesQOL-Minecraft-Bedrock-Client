from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor

from .. import __version__
from ..game.math3d import facing
from ..ui.render import rainbow_at
from .base import Module
from .settings import BoolSetting, ColorSetting, SliderSetting

PAD = 6


class Hud(Module):
    name = "HUD"
    description = "Watermark, coordinates, facing, FPS and the list of enabled modules."
    enabled_by_default = True

    def setup(self) -> None:
        self.add(BoolSetting("watermark", "Watermark", True))
        self.add(BoolSetting("arraylist", "Enabled module list", True))
        self.add(BoolSetting("coords", "Coordinates", True))
        self.add(BoolSetting("nether_coords", "Nether / Overworld coordinates", True))
        self.add(BoolSetting("facing", "Facing direction", True))
        self.add(BoolSetting("fps", "Overlay FPS", True))
        self.add(BoolSetting("entity_count", "Entity count", False))
        self.add(ColorSetting("accent", "Accent color (watermark, labels, list bar)", (255, 120, 40, 255)))
        self.add(BoolSetting("rainbow", "RGB accent (rainbow)", False))
        self.add(SliderSetting("rainbow_speed", "RGB speed", 1.0, 0.1, 5.0, 0.1))
        self.add(ColorSetting("text", "Text color", (235, 235, 235, 255)))
        self.add(BoolSetting("mc_font", "Minecraft font (all overlay text)", False))

    def accent(self, y: float = 0.0, height: float = 1080.0) -> QColor:
        """The accent color; in RGB mode it depends on screen height so the colors roll downward."""
        if self.val("rainbow"):
            return rainbow_at(y, height, self.val("rainbow_speed"))
        return self.settings["accent"].qcolor

    def on_render(self, ctx) -> None:
        text = self.settings["text"].qcolor
        if self.val("watermark"):
            w = ctx.text(PAD, PAD, "Ashes", self.accent(PAD, ctx.height))
            ctx.text(PAD + w, PAD, f"QOL v{__version__}", text)
        if self.val("arraylist"):
            self._draw_arraylist(ctx, text)
        self._draw_info(ctx, text)

    def _draw_arraylist(self, ctx, text) -> None:
        names = [m.name for m in ctx.modules if m.enabled and m is not self and m.toggleable]
        names.sort(key=lambda n: ctx.text_size(n)[0], reverse=True)
        y = PAD
        for name in names:
            w, h = ctx.text_size(name)
            right = ctx.width - PAD
            ctx.painter.fillRect(QRectF(right - w - 8, y, w + 8, h + 2), QColor(0, 0, 0, 110))
            ctx.painter.fillRect(QRectF(right, y, 2, h + 2), self.accent(y + h / 2, ctx.height))
            ctx.text(right - w - 4, y + 1, name, text)
            y += h + 2

    def _info_lines(self, ctx) -> list[tuple[str, str]]:
        state = ctx.state
        lines = []
        if not state.valid or state.player is None:
            lines.append(("Status", state.reason or "no data"))
        else:
            p = state.player
            if self.val("coords"):
                lines.append(("XYZ", f"{p.pos.x:.1f}, {p.pos.y:.1f}, {p.pos.z:.1f}"))
            if self.val("nether_coords"):
                if p.dimension == "overworld":
                    lines.append(("Nether", f"{p.pos.x / 8:.1f}, {p.pos.z / 8:.1f}"))
                elif p.dimension == "nether":
                    lines.append(("Overworld", f"{p.pos.x * 8:.1f}, {p.pos.z * 8:.1f}"))
            if self.val("facing"):
                direction, axis = facing(p.yaw)
                lines.append(("Facing", f"{direction} ({axis})  {p.yaw:.1f} / {p.pitch:.1f}"))
            if self.val("entity_count"):
                lines.append(("Entities", str(len(state.entities))))
        if self.val("fps"):
            lines.append(("FPS", f"{ctx.fps:.0f}"))
        return lines

    def _draw_info(self, ctx, text) -> None:
        lines = self._info_lines(ctx)
        _, h = ctx.text_size("X")
        y = ctx.height - PAD - h * len(lines)
        for label, value in lines:
            w = ctx.text(PAD, y, f"{label} ", self.accent(y + h / 2, ctx.height))
            ctx.text(PAD + w, y, value, text)
            y += h
