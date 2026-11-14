"""Per-frame drawing context handed to every module's on_render()."""
import time
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen

from ..game.math3d import Camera
from ..game.state import GameState

SHADOW = QColor(0, 0, 0, 200)


def make_camera(state: GameState, fov: float, width: float, height: float):
    if not state.valid or state.player is None or width <= 0 or height <= 0:
        return None
    p = state.player
    return Camera(p.eye_pos, p.yaw, p.pitch, state.fov or fov, width, height)


@dataclass
class RenderContext:
    painter: QPainter
    width: float
    height: float
    state: GameState
    camera: Camera | None
    fps: float
    modules: list
    font: QFont

    def scaled_font(self, scale: float) -> QFont:
        f = QFont(self.font)
        if self.font.pixelSize() > 0:     # pixel font (Minecraft): whole 8 px steps keep it crisp
            f.setPixelSize(max(8, round(self.font.pixelSize() * scale / 8) * 8))
        else:
            f.setPointSizeF(max(4.0, self.font.pointSizeF() * scale))
        return f

    def text_size(self, text: str, font: QFont | None = None) -> tuple[float, float]:
        m = QFontMetricsF(font or self.font)
        return m.horizontalAdvance(text), m.height()

    def text(self, x: float, y: float, text: str, color: QColor, align: str = "left",
             font: QFont | None = None, shadow: bool = True) -> float:
        """Draw text with its top edge at y. align: left | center | right. Returns width."""
        font = font or self.font
        m = QFontMetricsF(font)
        w = m.horizontalAdvance(text)
        if align == "center":
            x -= w / 2
        elif align == "right":
            x -= w
        baseline = y + m.ascent()
        p = self.painter
        p.setFont(font)
        if shadow:
            p.setPen(SHADOW)
            p.drawText(QPointF(x + 1, baseline + 1), text)
        p.setPen(color)
        p.drawText(QPointF(x, baseline), text)
        return w

    def outlined_line(self, x1, y1, x2, y2, color: QColor, width: float = 1.5) -> None:
        p = self.painter
        p.setPen(QPen(QColor(0, 0, 0, min(160, color.alpha())), width + 2))
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        p.setPen(QPen(color, width))
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def outlined_rect(self, rect: QRectF, color: QColor, width: float = 1.5) -> None:
        p = self.painter
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, min(160, color.alpha())), width + 2))
        p.drawRect(rect)
        p.setPen(QPen(color, width))
        p.drawRect(rect)


def rainbow(speed: float = 1.0, offset: float = 0.0, alpha: int = 255) -> QColor:
    """Hue cycling over time ("RGB"). offset (0..1) shifts the hue, e.g. per line for a wave."""
    hue = (time.perf_counter() * 0.2 * speed + offset) % 1.0
    color = QColor.fromHsvF(hue, 0.75, 1.0)
    color.setAlpha(alpha)
    return color


def rainbow_at(y: float, height: float, speed: float = 1.0, alpha: int = 255) -> QColor:
    """RGB that "rolls down the screen": the hue depends on screen height and time, so bands of
    color travel downward continuously across everything drawn with it."""
    span = max(height, 1.0)
    hue = (time.perf_counter() * 0.25 * speed - (y / span) * 0.7) % 1.0
    color = QColor.fromHsvF(hue, 0.7, 1.0)
    color.setAlpha(alpha)
    return color


def health_color(fraction: float) -> QColor:
    """Red -> yellow -> green as health goes 0 -> 1."""
    f = max(0.0, min(1.0, fraction))
    if f < 0.5:
        return QColor(255, int(510 * f), 40)
    return QColor(int(510 * (1 - f)), 255, 40)
