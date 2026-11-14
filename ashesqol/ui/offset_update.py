"""Asks to update the offsets when Minecraft's version doesn't match, runs it and reports back."""
import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from ..game.rediscovery import Rediscovery

log = logging.getLogger(__name__)


class OffsetUpdater:
    def __init__(self, app):
        self.app = app
        self.job: Rediscovery | None = None
        self._asked: set[str] = set()          # versions already asked about this session

    # --- called about once a second by the app ----------------------------------------------
    def check(self) -> None:
        if self.job is not None:
            if self.job.done:
                self._finish()
            return
        p, cfg = self.app.process, self.app.config
        if p.pm is None or not p.version or self.app.offsets.supports(p.version) or cfg["ignore_version_check"]:
            return
        if p.version not in self._asked:
            self._asked.add(p.version)
            self.ask(manual=False)

    def notice(self) -> str:
        if self.job is not None and not self.job.done:
            return f"Updating offsets for Minecraft {self.app.process.version}: {self.job.status}"
        return ""

    # --- dialogs ------------------------------------------------------------------------------------
    def _box(self, icon, title: str, text: str) -> QMessageBox:
        box = QMessageBox(icon, title, text)
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)   # above the game and overlay
        return box

    def ask(self, manual: bool = True) -> None:
        """Offer the automatic update. manual=True: opened from the settings window."""
        if self.job is not None and not self.job.done:
            return
        p, offsets = self.app.process, self.app.offsets
        if p.pm is None or not p.version:
            self._box(QMessageBox.Icon.Information, "AshesQOL",
                      "Start Minecraft first (with Data source set to Memory), then try again.").exec()
            return
        if offsets.supports(p.version):
            text = (f"The offsets already match Minecraft {p.version}.\n\n"
                    "Run the automatic update anyway? This re-finds every value from scratch and "
                    "only saves them if they all check out.")
        else:
            text = (f"Minecraft {p.version} is running, but AshesQOL's offsets are for "
                    f"{offsets.exe_version}. Until they're updated, ESP and the other modules can't "
                    "find the game's data.\n\n"
                    "Update automatically: AshesQOL searches the game's memory and re-finds every "
                    "value (about 2–3 minutes, in the background). You need to be in a world, "
                    "single-player or a Realm. Nothing is changed unless every value checks out, "
                    "and the old offsets are backed up.\n\n"
                    "Try anyway: use the current offsets as they are (works if this update didn't "
                    "move anything).")
        box = self._box(QMessageBox.Icon.Question, "AshesQOL: Minecraft version changed" if not manual
                        else "AshesQOL: update offsets", text)
        update = box.addButton("Update automatically", QMessageBox.ButtonRole.AcceptRole)
        anyway = None if offsets.supports(p.version) else box.addButton("Try anyway", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Not now", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(update)
        box.exec()
        clicked = box.clickedButton()
        if clicked is update:
            self.start()
        elif anyway is not None and clicked is anyway:
            self.app.config["ignore_version_check"] = True
            self.app.control.sync_general()

    def start(self) -> None:
        log.info("Starting automatic offset update for Minecraft %s", self.app.process.version)
        self.job = Rediscovery(self.app.process, self.app.offsets)

    def _finish(self) -> None:
        job, self.job = self.job, None
        if job.ok:
            self.app.offsets.data = job.result                 # shared by the providers: applies live
            self.app.providers["memory"].reset()
            self.app.config["ignore_version_check"] = False
            self.app.control.sync_general()
            self._box(QMessageBox.Icon.Information, "AshesQOL: offsets updated",
                      f"The offsets now match Minecraft {self.app.process.version}.\n\n"
                      f"The previous ones were saved as {job.backup_path.name}.").exec()
        else:
            self._box(QMessageBox.Icon.Warning, "AshesQOL: automatic update failed",
                      f"Nothing was changed.\n\nReason: {job.error}.\n\n"
                      "If you weren't in a world, join one and use 'Update offsets…' in the settings "
                      "window to try again. Otherwise this update needs a manual offset update.").exec()

    def shutdown(self) -> None:
        if self.job is not None:
            self.job.stop()
