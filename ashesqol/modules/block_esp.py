from PyQt6.QtCore import QLineF, QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF

from ..game.blocks import DEFAULT_SELECTION, default_color
from ..game.math3d import Vec3
from .base import Module
from .settings import BlockListSetting, BoolSetting, SliderSetting

# Cube corners: index = x_bit*4 + y_bit*2 + z_bit. Edges join corners differing in one bit.
_CORNERS = [(dx, dy, dz) for dx in (0, 1) for dy in (0, 1) for dz in (0, 1)]
_EDGES = [(i, i | bit) for i in range(8) for bit in (1, 2, 4) if not i & bit]


def _hull(points):
    """Convex hull (monotone chain) of the projected cube corners = the box's silhouette."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


class BlockEsp(Module):
    name = "BlockESP"
    description = "Highlights chosen blocks (chests, spawners, ores, ...) through walls."

    def setup(self) -> None:
        self.add(BlockListSetting("blocks", "Blocks", {b: default_color(b) for b in DEFAULT_SELECTION}))
        self.add(SliderSetting("range", "Range (blocks)", 48, 8, 160, 1))
        self.add(SliderSetting("max_blocks", "Max boxes drawn", 200, 20, 2000, 10))
        self.add(SliderSetting("line_width", "Line width", 1.5, 0.5, 5.0, 0.5))
        self.add(BoolSetting("fill", "Fill boxes", True))
        self.add(BoolSetting("outline", "Dark outline behind lines (much slower)", False))
        self.add(BoolSetting("smooth", "Smooth (antialiased) lines (slower)", False))
        self.add(BoolSetting("tracers", "Tracers", False))
        self.add(BoolSetting("labels", "Labels on nearby blocks", True))
        self.add(SliderSetting("label_range", "Label range (blocks)", 12, 2, 64, 1))
        self._cache_key = None
        self._cache_origin = None
        self._cache: list = []

    def wanted_blocks(self) -> set[str]:
        return set(self.val("blocks"))

    def block_range(self) -> float:
        return self.val("range")

    def _candidates(self, state, colors, origin, max_range, limit):
        """Nearest blocks, recomputed only when the hit list changes (about once a second) or we moved far.

        Keeps 2x the draw limit with some extra range, so walking between refreshes stays accurate.
        """
        key = (id(state.blocks), tuple(colors), max_range, limit)
        moved = self._cache_origin is None or self._cache_origin.distance(origin) > 8
        if key != self._cache_key or moved:
            reach = max_range + 16
            near = []
            for b in state.blocks:
                if b.block in colors:
                    center = Vec3(b.x + 0.5, b.y + 0.5, b.z + 0.5)
                    d = center.distance(origin)
                    if d <= reach:
                        near.append((d, b, center))
            near.sort(key=lambda h: h[0])
            self._cache = [(b, c) for _, b, c in near[: limit * 2]]
            self._cache_key, self._cache_origin = key, origin
        return self._cache

    def on_render(self, ctx) -> None:
        state, cam = ctx.state, ctx.camera
        if cam is None or not state.valid or state.player is None:
            return

        colors = self.val("blocks")
        origin = state.player.eye_pos
        max_range = self.val("range")
        limit = int(self.val("max_blocks"))
        hits = []
        for b, center in self._candidates(state, colors, origin, max_range, limit):
            dist = center.distance(origin)
            if dist <= max_range:
                hits.append((dist, b, center))
        hits.sort(key=lambda h: h[0])
        hits = hits[:limit]

        # Batch by color: one outline pass, one fill path and one drawLines call per color,
        # instead of ~30 Qt calls per box.
        fill_on, tracers_on = self.val("fill"), self.val("tracers")
        labels_on, label_range = self.val("labels"), self.val("label_range")
        groups: dict[tuple, tuple[list, QPainterPath]] = {}
        all_lines: list[QLineF] = []
        labels = []
        bottom = QPointF(ctx.width / 2, ctx.height)
        # Camera-space images of the world axes: corner (dx,dy,dz) = corner0 + dx*ax + dy*ay + dz*az.
        r, u, f = cam.right, cam.up, cam.forward
        ax, ay, az = (r.x, u.x, f.x), (r.y, u.y, f.y), (r.z, u.z, f.z)
        steps = [tuple(dx * ax[k] + dy * ay[k] + dz * az[k] for k in range(3)) for dx, dy, dz in _CORNERS]
        half_w, half_h, focal = cam.width / 2, cam.height / 2, cam.focal
        for dist, b, center in hits:
            c0 = cam.to_camera(Vec3(b.x, b.y, b.z))
            pts = []
            for sx, sy, sz in steps:
                z = c0[2] + sz
                if z < 0.05:
                    break
                pts.append((half_w + (c0[0] + sx) * focal / z, half_h - (c0[1] + sy) * focal / z))
            if len(pts) < 8:
                continue
            rgba = colors[b.block]
            lines, path = groups.setdefault(rgba, ([], QPainterPath()))
            box = [QLineF(*pts[a], *pts[c]) for a, c in _EDGES]
            if tracers_on:
                p = cam.project(center)
                if p:
                    box.append(QLineF(bottom, QPointF(*p)))
            lines.extend(box)
            all_lines.extend(box)
            if fill_on:
                path.addPolygon(QPolygonF([QPointF(x, y) for x, y in _hull(pts)]))
            if labels_on and dist <= label_range:
                top = cam.project(Vec3(b.x + 0.5, b.y + 1.15, b.z + 0.5))
                if top:
                    labels.append((top, f"{b.block.replace('_', ' ')}  {dist:.0f}m", rgba))

        width = self.val("line_width")
        painter = ctx.painter
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, self.val("smooth"))
        if fill_on:
            painter.setPen(Qt.PenStyle.NoPen)
            for rgba, (_, path) in groups.items():
                fill = QColor(*rgba)
                fill.setAlpha(min(40, fill.alpha()))
                path.setFillRule(Qt.FillRule.WindingFill)
                painter.fillPath(path, fill)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.val("outline"):
            painter.setPen(QPen(QColor(0, 0, 0, 150), width + 2))
            painter.drawLines(all_lines)
        for rgba, (lines, _) in groups.items():
            painter.setPen(QPen(QColor(*rgba), width))
            painter.drawLines(lines)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)   # text always smooth
        for top, text, rgba in labels:
            ctx.text(top[0], top[1] - 14, text, QColor(*rgba), align="center")
