"""Finds the running Minecraft process/window and (optionally) opens it for memory reads."""
import logging

import pymem
import pymem.process

from . import win32

log = logging.getLogger(__name__)

PROCESS_NAME = "Minecraft.Windows.exe"


def find_pid(name: str = PROCESS_NAME):
    for entry in pymem.process.list_processes():
        if entry.szExeFile.decode(errors="ignore").lower() == name.lower():
            return entry.th32ProcessID
    return None


class GameProcess:
    def __init__(self):
        self.pid = None
        self.hwnd = None
        self.pm: pymem.Pymem | None = None
        self.base_address = None
        self.module_size = None
        self.attach_error: str | None = None

    def _reset(self):
        if self.pm is not None:
            try:
                self.pm.close_process()
            except Exception:  # process may already be gone
                pass
        self.pid = self.hwnd = self.pm = None
        self.base_address = self.module_size = None
        self.attach_error = None

    def refresh(self, want_memory: bool) -> None:
        """Called about once a second: track the process, its window, and attach if asked."""
        pid = find_pid()
        if pid != self.pid:
            self._reset()
            self.pid = pid
            if pid:
                log.info("Found %s (pid %d)", PROCESS_NAME, pid)
        if self.pid is None:
            return
        if not win32.is_window(self.hwnd):
            self.hwnd = win32.find_game_window(self.pid)
        if want_memory and self.pm is None and self.attach_error is None:
            self._attach()

    def retry_attach(self) -> None:
        self.attach_error = None

    def _attach(self) -> None:
        try:
            pm = pymem.Pymem()
            pm.open_process_from_id(self.pid)
            module = pymem.process.module_from_name(pm.process_handle, PROCESS_NAME)
            if module is None:
                raise RuntimeError(f"module {PROCESS_NAME} not found in process")
            self.base_address = module.lpBaseOfDll
            self.module_size = module.SizeOfImage
            self.pm = pm
            log.info("Attached: base=0x%X size=0x%X", self.base_address, self.module_size)
        except Exception as e:
            self.attach_error = str(e) or type(e).__name__
            log.warning("Attach failed: %s", self.attach_error)
