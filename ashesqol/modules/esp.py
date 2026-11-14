from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor

from ..ui.render import health_color
from .common import EntityModule
from .settings import BoolSetting, ChoiceSetting, SliderSetting

# Box corners come from Entity.aabb_corners(): index = x_bit*4 + y_bit*2 + z_bit.
# Edges join corners that differ in exactly one bit.
_EDGES = [(i, i | bit) for i in range(8) for bit in (1, 2, 4) if not i & bit]


class Esp(EntityModule):
    name = "ESP"
    description = "Draws boxes around entities."
    enabled_by_default = True

    def setup(self) -> None:
        self.add(ChoiceSetting("mode", "Mode", "2D", ["2D", "3D"]))
        self.add(SliderSetting("line_width", "Line width", 1.5, 0.5, 5.0, 0.5))
        self.add(BoolSetting("fill", "Fill boxes", False))
        self.add(BoolSetting("health_bar", "Health bar", True))
        super().setup()

    def on_render(self, ctx) -> None:
        cam = ctx.camera
        width = self.val("line_width")
        for e, _dist, color in self.targets(ctx):
            pts = [cam.project(c) for c in e.aabb_corners()]
            if any(p is None for p in pts):
                continue  # partially behind the camera
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            rect = QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

            if self.val("fill"):
                fill = QColor(color)
                fill.setAlpha(45)
                ctx.painter.fillRect(rect, fill)
            if self.val("mode") == "3D":
                for a, b in _EDGES:
                    ctx.outlined_line(*pts[a], *pts[b], color, width)
            else:
                ctx.outlined_rect(rect, color, width)

            if self.val("health_bar") and e.health is not None and e.max_health:
                frac = max(0.0, min(1.0, e.health / e.max_health))
                bar = QRectF(rect.left() - 6, rect.top(), 3, rect.height())
                ctx.painter.fillRect(bar.adjusted(-1, -1, 1, 1), QColor(0, 0, 0, 170))
                filled = QRectF(bar.left(), bar.bottom() - bar.height() * frac, bar.width(), bar.height() * frac)
                ctx.painter.fillRect(filled, health_color(frac))
