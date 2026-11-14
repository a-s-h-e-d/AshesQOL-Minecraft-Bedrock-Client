"""Draws AshesQOL's icon (an ember rising from ash) and saves ashesqol/data/icon.ico.

    python make_icon.py [preview.png]
"""
import sys
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPainterPath, QRadialGradient
from PyQt6.QtWidgets import QApplication


def flame(cx: float, base: float, w: float, h: float) -> QPainterPath:
    """Teardrop flame with a flicked tip, centred on cx, standing on y=base."""
    p = QPainterPath()
    p.moveTo(cx, base)
    p.cubicTo(cx - w * 0.62, base, cx - w * 0.58, base - h * 0.55, cx - w * 0.18, base - h * 0.78)
    p.cubicTo(cx - w * 0.02, base - h * 0.9, cx + w * 0.02, base - h * 0.96, cx + w * 0.06, base - h)
    p.cubicTo(cx + w * 0.16, base - h * 0.82, cx + w * 0.62, base - h * 0.6, cx + w * 0.55, base - h * 0.28)
    p.cubicTo(cx + w * 0.5, base - h * 0.05, cx + w * 0.25, base, cx, base)
    return p


def render(size: int) -> QImage:
    s = float(size)
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)

    # charcoal tile with a faint warm glow from below
    bg = QLinearGradient(0, 0, 0, s)
    bg.setColorAt(0, QColor(30, 30, 38))
    bg.setColorAt(1, QColor(18, 18, 24))
    p.setBrush(QBrush(bg))
    p.drawRoundedRect(QRectF(0, 0, s, s), s * 0.22, s * 0.22)
    glow = QRadialGradient(QPointF(s * 0.5, s * 0.78), s * 0.5)
    glow.setColorAt(0, QColor(255, 110, 30, 90))
    glow.setColorAt(1, QColor(255, 110, 30, 0))
    p.setBrush(QBrush(glow))
    p.drawRoundedRect(QRectF(0, 0, s, s), s * 0.22, s * 0.22)

    # ash mound
    ash = QPainterPath()
    ash.moveTo(s * 0.2, s * 0.8)
    ash.cubicTo(s * 0.3, s * 0.7, s * 0.7, s * 0.7, s * 0.8, s * 0.8)
    ash.closeSubpath()
    ash_grad = QLinearGradient(0, s * 0.7, 0, s * 0.8)
    ash_grad.setColorAt(0, QColor(120, 120, 130))
    ash_grad.setColorAt(1, QColor(70, 70, 80))
    p.setBrush(QBrush(ash_grad))
    p.drawPath(ash)

    # outer flame: orange to red
    outer = QLinearGradient(0, s * 0.14, 0, s * 0.76)
    outer.setColorAt(0, QColor(255, 196, 70))
    outer.setColorAt(0.5, QColor(255, 120, 40))
    outer.setColorAt(1, QColor(220, 55, 30))
    p.setBrush(QBrush(outer))
    p.drawPath(flame(s * 0.5, s * 0.76, s * 0.46, s * 0.62))
    # inner core: bright yellow-white
    inner = QLinearGradient(0, s * 0.4, 0, s * 0.76)
    inner.setColorAt(0, QColor(255, 240, 170))
    inner.setColorAt(1, QColor(255, 170, 60))
    p.setBrush(QBrush(inner))
    p.drawPath(flame(s * 0.51, s * 0.76, s * 0.22, s * 0.33))

    # two rising sparks (skipped at tiny sizes, where they'd just be noise)
    if size >= 48:
        p.setBrush(QColor(255, 170, 60))
        p.drawEllipse(QPointF(s * 0.72, s * 0.26), s * 0.028, s * 0.028)
        p.setBrush(QColor(255, 130, 40, 200))
        p.drawEllipse(QPointF(s * 0.27, s * 0.34), s * 0.02, s * 0.02)
    p.end()
    return img


def main() -> None:
    app = QApplication(sys.argv[:1])   # noqa: F841 - QPainter on images needs a QApplication
    out = Path(__file__).resolve().parent / "ashesqol" / "data" / "icon.ico"
    render(256).save(str(out), "ICO")
    print(f"saved {out}")
    if len(sys.argv) > 1:                      # optional preview strip at several sizes
        sizes = [256, 64, 32, 16]
        strip = QImage(sum(sizes) + 20 * len(sizes), 256, QImage.Format.Format_ARGB32)
        strip.fill(QColor(235, 235, 240))
        p = QPainter(strip)
        x = 0
        for sz in sizes:
            p.drawImage(x, 256 - sz, render(sz))
            x += sz + 20
        p.end()
        strip.save(sys.argv[1])
        print(f"preview {sys.argv[1]}")


if __name__ == "__main__":
    main()
