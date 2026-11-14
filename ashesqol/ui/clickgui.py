"""In-game click GUI (Future/Meteor style): category panels over the game, opened with a hotkey.

Left-click a module to toggle it, right-click to expand its settings inline. Drag panel headers
to move them; right-click a header to collapse it. Esc (or the hotkey) closes and gives focus
back to Minecraft. Panel positions are saved in config["clickgui"].
"""
from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PyQt6.QtWidgets import QColorDialog, QWidget

from ..core import win32
from ..modules.settings import BlockListSetting, BoolSetting, ChoiceSetting, ColorSetting, SliderSetting
from .block_picker import BlockPickerDialog
from .fonts import minecraft_family, pixel_font
from .keys import key_name, pretty

PANEL_W, HEADER_H, ROW_H, SET_H, SLIDER_H = 196, 26, 22, 20, 30
ACCENT = QColor(255, 120, 40)
TEXT, MUTED = QColor(232, 232, 236), QColor(150, 150, 160)
PANEL_BG, SETTING_BG, HOVER = QColor(18, 18, 24, 235), QColor(12, 12, 16, 240), QColor(255, 255, 255, 18)


@dataclass
class Panel:
    category: str
    x: float
    y: float
    open: bool = True


class ClickGui(QWidget):
    def __init__(self, app):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.app = app
        self.font_main = QFont("Segoe UI", 10)
        self.font_main.setWeight(QFont.Weight.DemiBold)
        self.font_small = QFont("Segoe UI", 9)
        self.font_header = QFont("Segoe UI", 10)
        self.font_header.setWeight(QFont.Weight.Bold)
        self.expanded: set[str] = set()
        self.listening = None            # module waiting for a keybind
        self._items: list[tuple[QRectF, str, object]] = []
        self._drag = None                # (panel, dx, dy)
        self._slider = None              # (setting, bar rect)
        self._hover_pos = QPointF(-1, -1)
        self.panel_w = PANEL_W
        self.panels = self._load_panels()
        self._mc_font = None
        self._apply_theme()
        self._anim = QTimer(self)                 # repaint while the RGB accent is animating
        self._anim.timeout.connect(self._animate)
        self._anim.start(33)

    # --- theme (from the ClickGUI module) ------------------------------------------------
    def _theme_module(self):
        return next((m for m in self.app.modules if m.name == "ClickGUI"), None)

    def _apply_theme(self) -> None:
        th = self._theme_module()
        if th is None:
            self.c_accent, self.c_panel, self.c_text = ACCENT, PANEL_BG, TEXT
            self.c_header_text, self.c_dim, use_mc = QColor(20, 20, 24), 90, False
        else:
            self.c_accent = th.accent()
            self.c_panel = th.settings["panel"].qcolor
            self.c_text = th.settings["text"].qcolor
            self.c_header_text = th.settings["header_text"].qcolor
            self.c_dim = int(th.val("dim"))
            use_mc = th.val("mc_font")
        self.c_setting = self.c_panel.darker(140)
        self.c_setting.setAlpha(min(255, self.c_panel.alpha() + 10))
        if use_mc != self._mc_font:
            self._mc_font = use_mc
            family = minecraft_family(self.app.process) if use_mc else None
            for attr, size, weight in (("font_main", 10, QFont.Weight.DemiBold), ("font_small", 9, QFont.Weight.Normal),
                                       ("font_header", 10, QFont.Weight.Bold)):
                if family:
                    f = pixel_font(family)
                else:
                    f = QFont("Segoe UI")
                    f.setPointSizeF(size)
                    f.setWeight(weight)
                setattr(self, attr, f)
            self.panel_w = 250 if family else PANEL_W     # the pixel font is wider
            self._separate_panels()

    def _acc(self, y: float) -> QColor:
        """Accent color at a height on screen (RGB mode rolls the colors downward)."""
        th = self._theme_module()
        return th.accent(y, self.height()) if th is not None else ACCENT

    def _animate(self) -> None:
        th = self._theme_module()
        if self.isVisible() and th is not None and th.val("rainbow"):
            self.update()

    # --- panels / persistence -------------------------------------------------------
    def _categories(self) -> list[str]:
        cats = []
        for m in self.app.modules:
            if m.category not in cats:
                cats.append(m.category)
        return cats

    def _load_panels(self) -> list[Panel]:
        saved = (self.app.config.data.get("clickgui") or {}).get("panels", {})
        panels = []
        for i, cat in enumerate(self._categories()):
            x, y, is_open = saved.get(cat, (40 + i * (self.panel_w + 24), 60, True))
            panels.append(Panel(cat, float(x), float(y), bool(is_open)))
        return panels

    def _separate_panels(self) -> None:
        """Push panels right until none overlap (e.g. after the wider Minecraft-font layout)."""
        gap = 16
        placed: list[Panel] = []
        for panel in sorted(self.panels, key=lambda p: (p.x, p.y)):
            moved = True
            while moved:
                moved = False
                for other in placed:
                    overlap_x = panel.x < other.x + self.panel_w + gap and other.x < panel.x + self.panel_w + gap
                    overlap_y = abs(panel.y - other.y) < HEADER_H * 3
                    if overlap_x and overlap_y:
                        panel.x = other.x + self.panel_w + gap
                        moved = True
            placed.append(panel)

    def _save_panels(self) -> None:
        self.app.config["clickgui"] = {"panels": {p.category: [p.x, p.y, p.open] for p in self.panels}}

    # --- open / close ------------------------------------------------------------------
    def open_over(self, rect: QRect) -> None:
        self.setGeometry(rect)
        self._separate_panels()
        for p in self.panels:     # keep panels reachable if the window got smaller
            p.x = min(max(0.0, p.x), max(0.0, rect.width() - self.panel_w))
            p.y = min(max(0.0, p.y), max(0.0, rect.height() - HEADER_H))
        self.show()
        self.raise_()
        self.activateWindow()
        win32.force_foreground(int(self.winId()))
        self.setFocus()

    def close_gui(self) -> None:
        self.listening = self._drag = self._slider = None
        self._save_panels()
        self.hide()
        win32.force_foreground(self.app.process.hwnd)     # back to the game

    # --- drawing -------------------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._apply_theme()
        p.fillRect(self.rect(), QColor(0, 0, 0, self.c_dim))
        self._items = []
        self._hint_override = None
        hovered_module = None
        for panel in self.panels:
            hovered_module = self._draw_panel(p, panel) or hovered_module
        hint = ("Left-click: toggle  ·  Right-click: settings  ·  Drag headers  ·  "
                f"Esc / {pretty(self.app.config['clickgui_key'])}: close  ·  "
                f"{pretty(self.app.config['menu_key'])}: full settings window")
        p.setFont(self.font_small)
        p.setPen(MUTED)
        p.drawText(QRectF(0, self.height() - 28, self.width(), 20), Qt.AlignmentFlag.AlignCenter, hint)
        hover_text = self._hint_override or (hovered_module.description if hovered_module is not None else "")
        if hover_text:
            p.setPen(self.c_text)
            p.drawText(QRectF(0, self.height() - 50, self.width(), 20), Qt.AlignmentFlag.AlignCenter, hover_text)
        p.end()

    def _hovered(self, rect: QRectF) -> bool:
        return rect.contains(self._hover_pos)

    def _draw_panel(self, p: QPainter, panel: Panel):
        hovered_module = None
        mods = [m for m in self.app.modules if m.category == panel.category]
        header = QRectF(panel.x, panel.y, self.panel_w, HEADER_H)
        th = self._theme_module()
        header_color = self._acc(panel.y + HEADER_H / 2)
        p.fillRect(header, header_color)
        p.setFont(self.font_header)
        p.setPen(self.c_header_text)
        p.drawText(header.adjusted(10, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter, panel.category)
        toggleable = [m for m in mods if m.toggleable]
        count = f"{sum(m.enabled for m in toggleable)}/{len(toggleable)}  " if toggleable else ""
        p.drawText(header.adjusted(10, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                   f"{count}{'−' if panel.open else '+'}")
        self._items.append((header, "header", panel))
        if not panel.open:
            return None
        y = panel.y + HEADER_H
        for m in mods:
            row = QRectF(panel.x, y, self.panel_w, ROW_H)
            self.c_accent = self._acc(y + ROW_H / 2)
            p.fillRect(row, self.c_panel)
            if self._hovered(row):
                p.fillRect(row, HOVER)
                hovered_module = m
            if m.enabled:
                p.fillRect(QRectF(row.left(), row.top(), 3, row.height()), self.c_accent)
            p.setFont(self.font_main)
            p.setPen(self.c_accent if m.enabled else self.c_text)
            p.drawText(row.adjusted(12, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter, m.name)
            p.setPen(MUTED)
            p.drawText(row.adjusted(12, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       "▾" if m.name in self.expanded else "▸")
            self._items.append((row, "module", m))
            y += ROW_H
            if m.name in self.expanded:
                y = self._draw_settings(p, m, panel.x, y)
        p.fillRect(QRectF(panel.x, y, self.panel_w, 3), self.c_panel)
        return hovered_module

    def _draw_settings(self, p: QPainter, m, x: float, y: float) -> float:
        inner = lambda r: r.adjusted(16, 0, -10, 0)   # noqa: E731
        p.setFont(self.font_small)
        # keybind row
        row = QRectF(x, y, self.panel_w, SET_H)
        self.c_accent = self._acc(y + SET_H / 2)
        p.fillRect(row, self.c_setting)
        if self._hovered(row):
            p.fillRect(row, HOVER)
        p.setPen(MUTED)
        text = "Press a key… (Esc clears)" if self.listening is m else f"Bind: {pretty(m.keybind)}"
        p.drawText(inner(row), Qt.AlignmentFlag.AlignVCenter, text)
        self._items.append((row, "bind", m))
        y += SET_H
        for s in m.settings.values():
            h = SLIDER_H if isinstance(s, SliderSetting) else SET_H
            row = QRectF(x, y, self.panel_w, h)
            self.c_accent = self._acc(y + h / 2)
            p.fillRect(row, self.c_setting)
            if self._hovered(row):
                p.fillRect(row, HOVER)
            label_rect = QRectF(row.left(), row.top(), row.width(), SET_H)
            p.setPen(self.c_text)
            room = self.panel_w - 26 - (40 if isinstance(s, (BoolSetting, ColorSetting)) else 70)
            label = QFontMetricsF(self.font_small).elidedText(s.label, Qt.TextElideMode.ElideRight, room)
            p.drawText(inner(label_rect), Qt.AlignmentFlag.AlignVCenter, label)
            if label != s.label and self._hovered(row):
                self._hint_override = s.label
            right = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight
            if isinstance(s, BoolSetting):
                box = QRectF(row.right() - 22, row.top() + 5, 11, 11)
                p.setPen(QPen(self.c_accent if s.value else MUTED, 1))
                p.setBrush(self.c_accent if s.value else Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(box, 2, 2)
                p.setBrush(Qt.BrushStyle.NoBrush)
            elif isinstance(s, SliderSetting):
                p.setPen(self.c_accent)
                p.drawText(inner(label_rect), right, f"{s.value:.{s.decimals}f}")
                bar = QRectF(row.left() + 16, row.top() + SET_H + 1, self.panel_w - 26, 4)
                p.fillRect(bar, QColor(60, 60, 70))
                frac = (s.value - s.minimum) / (s.maximum - s.minimum) if s.maximum > s.minimum else 0
                p.fillRect(QRectF(bar.left(), bar.top(), bar.width() * frac, bar.height()), self.c_accent)
                self._items.append((row, "slider", (s, bar)))
                y += h
                continue
            elif isinstance(s, ChoiceSetting):
                p.setPen(self.c_accent)
                p.drawText(inner(label_rect), right, f"‹ {s.value} ›")
            elif isinstance(s, ColorSetting):
                swatch = QRectF(row.right() - 30, row.top() + 5, 18, 10)
                p.fillRect(swatch, s.qcolor)
                p.setPen(QPen(MUTED, 1))
                p.drawRect(swatch)
            elif isinstance(s, BlockListSetting):
                p.setPen(self.c_accent)
                p.drawText(inner(label_rect), right, f"{len(s.value)} blocks ›")
            self._items.append((row, "setting", s))
            y += h
        return y

    # --- input ----------------------------------------------------------------------------
    def _hit(self, pos: QPointF):
        for rect, kind, payload in reversed(self._items):
            if rect.contains(pos):
                return kind, payload, rect
        return None, None, None

    def _changed(self) -> None:
        self.app.control.sync_modules()
        self.app.control.refresh_current()
        self.update()

    def mousePressEvent(self, event):
        pos = event.position()
        kind, payload, rect = self._hit(pos)
        left = event.button() == Qt.MouseButton.LeftButton
        right = event.button() == Qt.MouseButton.RightButton
        if kind == "header":
            if left:
                self._drag = (payload, pos.x() - payload.x, pos.y() - payload.y)
                self.panels.remove(payload)       # bring to front
                self.panels.append(payload)
            elif right:
                payload.open = not payload.open
        elif kind == "module":
            if left and payload.toggleable:
                payload.toggle()
            elif right or left:
                self.expanded ^= {payload.name}
        elif kind == "bind" and left:
            self.listening = payload
        elif kind == "slider" and left:
            self._slider = payload
            self._set_slider(pos.x())
        elif kind == "setting":
            self._click_setting(payload, left, right)
        self._changed()

    def _click_setting(self, s, left: bool, right: bool) -> None:
        if isinstance(s, BoolSetting) and left:
            s.set(not s.value)
        elif isinstance(s, ChoiceSetting) and (left or right):
            i = s.options.index(s.value)
            s.set(s.options[(i + (1 if left else -1)) % len(s.options)])
        elif isinstance(s, ColorSetting) and left:
            dialog = QColorDialog(s.qcolor, self)
            dialog.setWindowTitle(s.label)
            dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel)
            if self._run_dialog(dialog):
                s.set(dialog.currentColor().getRgb())
        elif isinstance(s, BlockListSetting) and left:
            dialog = BlockPickerDialog(s.value, self)
            if self._run_dialog(dialog):
                s.set(dialog.selection())

    def _run_dialog(self, dialog) -> bool:
        """Show a modal dialog *above* the click GUI.

        The GUI is always-on-top, so a normal dialog opens behind it: invisible, yet still blocking
        every click on the GUI (Windows plays the error sound). Making the dialog always-on-top too,
        centering it on the GUI and giving it focus fixes that.
        """
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        dialog.adjustSize()
        frame = dialog.frameGeometry()
        frame.moveCenter(self.geometry().center())
        dialog.move(frame.topLeft())

        def bring_forward():
            dialog.raise_()
            dialog.activateWindow()
            win32.force_foreground(int(dialog.winId()))

        QTimer.singleShot(0, bring_forward)      # once the dialog window exists
        accepted = bool(dialog.exec())
        self.activateWindow()                     # focus back to the GUI afterwards
        win32.force_foreground(int(self.winId()))
        return accepted

    def _set_slider(self, x: float) -> None:
        s, bar = self._slider
        frac = min(1.0, max(0.0, (x - bar.left()) / bar.width()))
        steps = round(frac * (s.maximum - s.minimum) / s.step)
        s.set(s.minimum + steps * s.step)

    def mouseMoveEvent(self, event):
        pos = event.position()
        self._hover_pos = pos
        if self._drag:
            panel, dx, dy = self._drag
            panel.x = min(max(0.0, pos.x() - dx), max(0.0, self.width() - self.panel_w))
            panel.y = min(max(0.0, pos.y() - dy), max(0.0, self.height() - HEADER_H))
        elif self._slider:
            self._set_slider(pos.x())
            self.app.control.refresh_current()
        self.update()

    def wheelEvent(self, event):
        """Scroll the panel under the mouse up/down (long expanded panels can run off-screen)."""
        pos = event.position()
        for panel in reversed(self.panels):
            if panel.x <= pos.x() <= panel.x + self.panel_w:
                panel.y += event.angleDelta().y() / 120 * 40
                panel.y = min(panel.y, max(0.0, self.height() - HEADER_H))
                break
        self.update()

    def mouseReleaseEvent(self, event):
        self._drag = self._slider = None

    def keyPressEvent(self, event):
        if self.listening is not None:
            if event.key() == Qt.Key.Key_Escape.value:
                self.listening.keybind = None
            else:
                name = key_name(event)
                if name is None:
                    return
                self.listening.keybind = name
            self.listening = None
            self._changed()
        elif event.key() == Qt.Key.Key_Escape.value:
            self.close_gui()
