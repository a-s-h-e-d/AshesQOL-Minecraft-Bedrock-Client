from ..game.math3d import Vec3
from ..ui.render import health_color
from .common import EntityModule
from .settings import BoolSetting, ChoiceSetting, SliderSetting

_TARGET_HEIGHT = {"Feet": 0.0, "Body": 0.5, "Head": 1.0}


class Tracers(EntityModule):
    name = "Tracers"
    description = "Draws lines from the screen to entities."
    enabled_by_default = True
    default_range = 128

    def setup(self) -> None:
        self.add(ChoiceSetting("origin", "Line origin", "Bottom", ["Center", "Bottom", "Top"]))
        self.add(ChoiceSetting("target", "Line target", "Body", list(_TARGET_HEIGHT)))
        self.add(SliderSetting("line_width", "Line width", 1.5, 0.5, 5.0, 0.5))
        self.add(BoolSetting("offscreen", "Point to off-screen entities", True))
        self.add(BoolSetting("distance_color", "Color by distance (red = close)", False))
        super().setup()

    def on_render(self, ctx) -> None:
        cam = ctx.camera
        ox = ctx.width / 2
        oy = {"Center": ctx.height / 2, "Bottom": ctx.height, "Top": 0.0}[self.val("origin")]
        height_frac = _TARGET_HEIGHT[self.val("target")]
        width = self.val("line_width")
        max_range = self.val("range")

        for e, dist, color in self.targets(ctx):
            point = e.pos + Vec3(0.0, e.height * height_frac, 0.0)
            if self.val("offscreen"):
                x, y, _ = cam.project_edge(point)
            else:
                projected = cam.project(point)
                if projected is None:
                    continue
                x, y = projected
            if self.val("distance_color"):
                color = health_color(dist / max_range)
            ctx.outlined_line(ox, oy, x, y, color, width)
