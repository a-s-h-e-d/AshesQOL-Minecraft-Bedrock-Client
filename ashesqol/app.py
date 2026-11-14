"""Wires everything together and runs the per-frame loop."""
import logging
import sys
import time

from PyQt6.QtCore import QRect, Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from . import APP_NAME
from .config import Config
from .paths import FROZEN, ICON_PATH, LOG_PATH
from .core import win32
from .core.offsets import Offsets
from .core.process import GameProcess
from .game.memory_provider import MemoryProvider
from .game.providers import MockProvider
from .game.reader import StateReader
from .game.state import GameState
from .modules import create_modules
from .modules.base import TickContext
from .ui.clickgui import ClickGui
from .ui.offset_update import OffsetUpdater
from .ui.control import ControlWindow
from .ui.overlay import Overlay, native_to_logical
from .ui.theme import STYLESHEET

log = logging.getLogger(__name__)

PREVIEW_SIZE = (1280, 720)


class AshesApp:
    def __init__(self, argv=None):
        self.qapp = QApplication.instance() or QApplication(argv or sys.argv)
        self.qapp.setApplicationName(APP_NAME)
        if ICON_PATH.exists():
            self.qapp.setWindowIcon(QIcon(str(ICON_PATH)))
        self.qapp.setStyleSheet(STYLESHEET)

        self.config = Config.load()
        self.modules = create_modules()
        for module in self.modules:
            module.load_json(self.config["modules"].get(module.name, {}))

        self.process = GameProcess()
        self.offsets = Offsets.load()
        self.providers = {p.key: p for p in (MockProvider(), MemoryProvider(self.process, self.offsets))}
        if self.config["source"] not in self.providers:
            self.config["source"] = "mock"
        self.state = GameState.invalid("starting")
        self.reader = StateReader()   # reads the game on its own thread; tick() uses its latest snapshot
        self.active = True          # master on/off switch (not saved: always starts on)
        self.keys = win32.KeyWatcher()

        self.overlay = Overlay(self)
        self.control = ControlWindow(self)
        self.clickgui = ClickGui(self)
        self.updater = OffsetUpdater(self)     # offers the automatic offset update after game updates

        self._last_tick = time.perf_counter()
        self._tick_failed: set[str] = set()
        self.timer = QTimer()
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.process_timer = QTimer()
        self.process_timer.timeout.connect(self.refresh_process)

    @property
    def provider(self):
        return self.providers[self.config["source"]]

    def set_source(self, key: str) -> None:
        self.config["source"] = key
        self.process.retry_attach()
        self.refresh_process()

    # --- loops ---------------------------------------------------------------
    def refresh_process(self) -> None:
        """Once per second: find the game process/window, attach if reading memory."""
        self.process.refresh(want_memory=self.config["source"] == "memory")
        self.control.set_status(self._status_text())
        self.updater.check()

    def _status_text(self) -> str:
        p = self.process
        if p.pid is None:
            return "Minecraft: not running"
        parts = [f"Minecraft {p.version or ''}".strip() + f": pid {p.pid}", "window found" if p.hwnd else "no window"]
        if p.pm is not None:
            parts.append(f"attached @ 0x{p.base_address:X}")
            if self.updater.notice():
                parts.append("updating offsets...")
            elif not self.offsets.supports(p.version):
                parts.append(f"UNSUPPORTED VERSION (offsets are for {self.offsets.exe_version})")
        elif p.attach_error:
            parts.append("attach failed")
        return "  ·  ".join(parts)

    def set_active(self, active: bool) -> None:
        """Master switch. Off = no memory reads, no module logic, overlay hidden."""
        if active == self.active:
            return
        self.active = active
        if not active:
            # Modules that change the game (e.g. Freecam) must undo it now, not just pause.
            for module in self.modules:
                if module.enabled and not module.persist_enabled:
                    module.set_enabled(False)
            self.overlay.hide()
            if self.clickgui.isVisible():
                self.clickgui.close_gui()
            self.reader.paused = True
            self.state = GameState.invalid("AshesQOL is disabled")
        if active:
            self.reader.paused = False
        log.info("AshesQOL %s", "enabled" if active else "disabled")
        self.control.sync_active()
        self.control.sync_modules()

    def tick(self) -> None:
        now = time.perf_counter()
        dt, self._last_tick = now - self._last_tick, now

        self._handle_keys()
        if not self.active:
            return
        self.providers["memory"].interpolate = self.config["interpolate"]
        self.providers["memory"].ignore_version = self.config["ignore_version_check"]
        self.provider.wanted_blocks = frozenset(b for m in self.modules if m.enabled for b in m.wanted_blocks())
        self.providers["memory"].block_range = max([m.block_range() for m in self.modules if m.enabled] or [0.0])
        self.reader.provider = self.provider
        self.state = self.reader.latest
        hwnd = self.process.hwnd
        ctx = TickContext(
            state=self.state, dt=dt,
            memory=self.provider if isinstance(self.provider, MemoryProvider) and self.state.valid else None,
            game_focused=bool(hwnd) and win32.foreground_window() == hwnd,
        )
        for module in self.modules:
            if module.enabled:
                try:
                    module.on_tick(ctx)
                except Exception:
                    if module.name not in self._tick_failed:  # log once, don't spam every frame
                        self._tick_failed.add(module.name)
                        log.exception("Module %s tick failed", module.name)
        self._place_overlay()
        if self.overlay.isVisible():
            self.overlay.repaint()   # paint now, with the data we just read (update() would queue it)

    def _handle_keys(self) -> None:
        menu_key, toggle_key, gui_key = (self.config["menu_key"], self.config["toggle_key"],
                                         self.config["clickgui_key"])
        names = {menu_key, toggle_key, gui_key} | {m.keybind for m in self.modules if m.keybind}
        pressed = self.keys.poll(names)
        if not pressed:
            return
        if self.clickgui.listening is not None:
            return                       # the click GUI is capturing a keybind
        if menu_key in pressed:
            self.control.toggle_visible()
        if toggle_key in pressed:
            self.set_active(not self.active)
        if gui_key in pressed:
            self.toggle_clickgui()
        hwnd = self.process.hwnd
        if self.active and hwnd and win32.foreground_window() == hwnd:
            changed = False
            for module in self.modules:
                if module.keybind and module.keybind in pressed:
                    module.toggle()
                    changed = True
            if changed:
                self.control.sync_modules()

    def toggle_clickgui(self) -> None:
        """Open the click GUI over the game (only while Minecraft or the preview is in front)."""
        if self.clickgui.isVisible():
            self.clickgui.close_gui()
            return
        hwnd = self.process.hwnd
        game_in_front = bool(hwnd) and win32.foreground_window() == hwnd
        if not self.active or not (game_in_front or self.overlay.preview):
            return
        self.clickgui.open_over(self.overlay.geometry())

    def _place_overlay(self) -> None:
        hwnd = self.process.hwnd
        rect = None
        if win32.is_window(hwnd) and not win32.is_minimized(hwnd):
            rect = win32.client_rect_on_screen(hwnd)

        if rect and rect[2] > 0 and rect[3] > 0:
            fg = win32.foreground_window()
            visible = (not self.config["only_when_focused"]
                       or fg in (hwnd, int(self.control.winId()), int(self.clickgui.winId())))
            geometry = native_to_logical(*rect)
            self.overlay.preview = False
        elif self.config["source"] == "mock":
            visible = True
            geometry = self._preview_rect()
            self.overlay.preview = self.config["preview_background"]
        else:
            visible, geometry = False, None

        if not visible:
            if self.overlay.isVisible():
                self.overlay.hide()
            return
        if self.overlay.geometry() != geometry:
            self.overlay.setGeometry(geometry)
        if not self.overlay.isVisible():
            self.overlay.show()

    def _preview_rect(self) -> QRect:
        area = self.qapp.primaryScreen().availableGeometry()
        w, h = min(PREVIEW_SIZE[0], area.width()), min(PREVIEW_SIZE[1], area.height())
        return QRect(area.x() + (area.width() - w) // 2, area.y() + (area.height() - h) // 2, w, h)

    # --- lifecycle -------------------------------------------------------------
    def save(self) -> None:
        self.config["modules"] = {m.name: m.to_json() for m in self.modules}
        self.config.save()
        log.info("Settings saved")

    def system_notices(self) -> list[str]:
        """Notices shown on the overlay regardless of which modules are on."""
        text = self.updater.notice()
        return [text] if text else []

    def quit(self) -> None:
        self.updater.shutdown()
        self.clickgui.hide()
        self.clickgui._save_panels()
        self.reader.stop()
        self.providers["memory"].shutdown()
        for module in self.modules:
            try:
                module.on_shutdown()
            except Exception:
                log.exception("Module %s shutdown failed", module.name)
        self.save()
        self.qapp.quit()

    def run(self) -> int:
        if self.config["show_control_on_start"]:
            self.control.show()
        else:
            log.info("Control window hidden on start: %s opens it, %s opens the click GUI",
                     self.config["menu_key"], self.config["clickgui_key"])
        self.refresh_process()
        self.process_timer.start(1000)
        fps = self.config["max_fps"] or self.qapp.primaryScreen().refreshRate() or 60
        fps = max(30, min(240, fps))
        log.info("Overlay running at %.0f FPS", fps)
        self.timer.start(max(1, int(1000 / fps)))
        return self.qapp.exec()


def run() -> int:
    # Background scanners share Python's GIL with the overlay; switching threads every 1 ms
    # (default 5 ms) keeps a busy scanner from delaying a frame by more than about a millisecond.
    sys.setswitchinterval(0.001)
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    if FROZEN:      # the exe has no console: keep a log file next to it
        logging.basicConfig(level=logging.INFO, format=fmt, filename=LOG_PATH, filemode="w", encoding="utf-8")
    else:
        logging.basicConfig(level=logging.INFO, format=fmt)
    logging.getLogger("pymem").setLevel(logging.WARNING)
    return AshesApp().run()
