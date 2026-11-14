"""Transparent, click-through, always-on-top window laid over the game's client area."""
import logging
import time

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from ..core import win32
from ..modules.common import EntityModule
from .fonts import overlay_font
from .render import RenderContext, make_camera

log = logging.getLogger(__name__)


def native_to_logical(x: int, y: int, w: int, h: int) -> QRect:
    """Convert a physical-pixel rect (Win32) to Qt logical coordinates on the right monitor.

    Qt keeps each screen's top-left at its native position and divides sizes by the
    screen's scale factor, so we do the same relative to the screen the rect is on.
    """
    cx, cy = x + w / 2, y + h / 2
    screens = QGuiApplication.screens()
    target = QGuiApplication.primaryScreen()
    for s in screens:
        g, dpr = s.geometry(), s.devicePixelRatio()
        if g.x() <= cx < g.x() + g.width() * dpr and g.y() <= cy < g.y() + g.height() * dpr:
            target = s
            break
    g, dpr = target.geometry(), target.devicePixelRatio()
    return QRect(round(g.x() + (x - g.x()) / dpr), round(g.y() + (y - g.y()) / dpr),
                 round(w / dpr), round(h / dpr))


class Overlay(QWidget):
    def __init__(self, app):
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool
                         | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowDoesNotAcceptFocus
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.app = app
        self.preview = False          # dim background + border when no game window
        self.font = overlay_font(False)
        self._mc_font = False
        self._fps = 0.0
        self._last_paint: float | None = None
        self._failed: set[str] = set()

    def showEvent(self, event):
        super().showEvent(event)
        win32.make_click_through(int(self.winId()))

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            self.draw(painter, self.width(), self.height())
        finally:
            painter.end()

    def _tick_fps(self) -> None:
        now = time.perf_counter()
        if self._last_paint is not None:
            dt = now - self._last_paint
            if dt > 0:
                self._fps = 1 / dt if self._fps == 0 else self._fps * 0.9 + (1 / dt) * 0.1
        self._last_paint = now

    def draw(self, painter: QPainter, width: float, height: float) -> None:
        """All overlay drawing. Separate from paintEvent so it can render to an image for tests."""
        self._tick_fps()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if self.preview:
            painter.fillRect(QRectF(0, 0, width, height), QColor(14, 14, 20, 150))
            painter.setPen(QPen(QColor(255, 120, 40, 160), 1, Qt.PenStyle.DashLine))
            painter.drawRect(QRectF(0.5, 0.5, width - 1, height - 1))

        state = self.app.state
        hud = next((m for m in self.app.modules if m.name == "HUD"), None)
        use_mc = bool(hud and hud.val("mc_font"))
        if use_mc != self._mc_font:
            self._mc_font = use_mc
            self.font = overlay_font(use_mc, self.app.process)
        ctx = RenderContext(
            painter=painter, width=width, height=height, state=state,
            camera=make_camera(state, self.app.config["fov"], width, height),
            fps=self._fps, modules=self.app.modules, font=self.font,
        )
        for module in self.app.modules:
            if not module.enabled:
                continue
            painter.save()
            try:
                module.on_render(ctx)
            except Exception:
                if module.name not in self._failed:  # log once, keep the overlay alive
                    self._failed.add(module.name)
                    log.exception("Module %s failed to render", module.name)
            finally:
                painter.restore()
        self._draw_notices(ctx, hud)

    def _draw_notices(self, ctx, hud) -> None:
        """Startup notices ("locating ...") for enabled modules, stacked at the top center."""
        wants = set()
        for m in self.app.modules:
            if m.enabled:
                if isinstance(m, EntityModule):
                    wants.add("entities")
                elif m.wanted_blocks():
                    wants.add("blocks")
        lines = self.app.system_notices() + [text for kind, text in ctx.state.notices if kind in wants]
        _, h = ctx.text_size("X")
        for i, text in enumerate(lines):
            y = 6 + i * (h + 2)
            color = hud.accent(y + h / 2, ctx.height) if hud is not None else QColor(255, 200, 120)
            ctx.text(ctx.width / 2, y, text, color, align="center")
