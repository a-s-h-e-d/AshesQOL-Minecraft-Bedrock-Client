"""Polls the data provider on its own thread, so memory reads never stall a frame.

Reading another process's memory occasionally stalls for 10-20 ms on a single read (the game
is touching that memory). If the overlay read memory itself, each stall would be a visible hitch.
Instead this thread keeps a fresh GameState (about 250 per second) and the overlay just draws
the latest one. ReadProcessMemory releases Python's GIL, so a stalled read here doesn't block
drawing.
"""
import logging
import threading
import time

from .state import GameState

log = logging.getLogger(__name__)


class StateReader:
    def __init__(self, interval: float = 1 / 250):
        self.interval = interval
        self.provider = None                  # set by the app; may change at any time
        self.paused = False
        self.latest: GameState = GameState.invalid("starting")
        self._failed = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="state-reader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        last = time.perf_counter()
        while not self._stop.is_set():
            started = time.perf_counter()
            dt, last = started - last, started
            provider = self.provider
            if provider is None or self.paused:
                self.latest = GameState.invalid("paused")
            else:
                try:
                    self.latest = provider.poll(dt)
                    self._failed = False
                except Exception:
                    if not self._failed:          # log once per failure streak
                        self._failed = True
                        log.exception("Reading game state failed")
            self._stop.wait(max(0.0005, self.interval - (time.perf_counter() - started)))
