from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor

from ..game.math3d import Vec3
from ..ui.render import health_color
from .common import EntityModule
from .settings import BoolSetting, SliderSetting


class Nametags(EntityModule):
    name = "Nametags"
    description = "Labels above entities with name, health and distance."
    enabled_by_default = True

    def setup(self) -> None:
        self.add(BoolSetting("show_health", "Show health", True))
        self.add(BoolSetting("show_distance", "Show distance", True))
        self.add(BoolSetting("background", "Background", True))
        self.add(SliderSetting("scale", "Scale", 1.0, 0.5, 2.5, 0.1))
        super().setup()

    def on_render(self, ctx) -> None:
        cam = ctx.camera
        font = ctx.scaled_font(self.val("scale"))
        gray = QColor(190, 190, 190)

        for e, dist, color in self.targets(ctx):
            projected = cam.project(e.pos + Vec3(0.0, e.height + 0.3, 0.0))
            if projected is None:
                continue
            parts = [(e.name, color)]
            if self.val("show_health") and e.health is not None:
                frac = e.health / e.max_health if e.max_health else 1.0
                parts.append((f" {e.health:.0f}♥", health_color(frac)))
            if self.val("show_distance"):
                parts.append((f" {dist:.0f}m", gray))

            widths = [ctx.text_size(t, font)[0] for t, _ in parts]
            _, h = ctx.text_size("X", font)
            total = sum(widths)
            x, y = projected[0] - total / 2, projected[1] - h - 2

            if self.val("background"):
                ctx.painter.fillRect(QRectF(x - 4, y - 2, total + 8, h + 4), QColor(0, 0, 0, 130))
            for (text, c), w in zip(parts, widths):
                ctx.text(x, y, text, c, font=font)
                x += w
