import math

from ..core.keyhook import KeyBlocker
from ..core.win32 import VK, key_down
from ..game.math3d import Vec3
from .base import Module, TickContext
from .settings import BoolSetting, ChoiceSetting, SliderSetting

WASD = "WASD + Space/Shift (blocks normal movement)"

# forward, back, left, right, up, down (+ boost key)
_SCHEMES = {
    WASD: ("W", "S", "A", "D", "SPACE", "LSHIFT", "LCONTROL"),
    "Arrows + PgUp/PgDn": ("UP", "DOWN", "LEFT", "RIGHT", "PAGEUP", "PAGEDOWN", "RSHIFT"),
    "Numpad 8/5/4/6 + 9/3": ("NUMPAD8", "NUMPAD5", "NUMPAD4", "NUMPAD6", "NUMPAD9", "NUMPAD3", "RSHIFT"),
}
_BLOCKED_VKS = {VK[k] for k in _SCHEMES[WASD]}


class Freecam(Module):
    name = "Freecam"
    category = "World"
    description = ("Fly the camera away from your body. With the WASD scheme, W/A/S/D, Space, Shift and Ctrl "
                   "are taken away from Minecraft while it's on (Ctrl = boost), so your real player stays put. "
                   "Look around with the mouse as usual. Your position is put back when you turn it off. "
                   "Needs the Memory data source. Works best in single-player.")
    persist_enabled = False   # never start the app with the camera detached

    def setup(self) -> None:
        self.add(ChoiceSetting("keys", "Movement keys", WASD, list(_SCHEMES)))
        self.add(SliderSetting("speed", "Speed (blocks/s)", 12, 1, 60, 1))
        self.add(BoolSetting("boost", "Boost key = 4x speed", True))
        self._game = None       # MemoryProvider we moved the player through
        self._start = None      # PlayerBody when freecam started
        self._offset = Vec3(0.0, 0.0, 0.0)
        self._focused = False
        self._blocker = KeyBlocker(_BLOCKED_VKS, should_block=lambda: self.enabled and self._focused)

    # --- lifecycle ---------------------------------------------------------------
    def on_enable(self) -> None:
        self._start = None
        self._offset = Vec3(0.0, 0.0, 0.0)

    def on_disable(self) -> None:
        self._blocker.uninstall()
        self._restore()

    def on_shutdown(self) -> None:
        self._blocker.uninstall()
        self._restore()

    def _restore(self) -> None:
        if self._game is not None and self._start is not None:
            self._game.write_player_body(self._start)  # no-op if the world changed
        self._game = self._start = None

    # --- input ---------------------------------------------------------------------
    def _pressed(self, name: str) -> bool:
        if self.val("keys") == WASD:
            return self._blocker.is_down(VK[name])
        return key_down(name)

    def _input(self, yaw_deg: float) -> tuple[Vec3, bool]:
        fwd, back, left, right, up, down, boost = (self._pressed(k) for k in _SCHEMES[self.val("keys")])
        yaw = math.radians(yaw_deg)
        forward = Vec3(-math.sin(yaw), 0.0, math.cos(yaw))
        right_vec = Vec3(-math.cos(yaw), 0.0, -math.sin(yaw))
        move = forward * (fwd - back) + right_vec * (right - left) + Vec3(0.0, float(up - down), 0.0)
        return move, boost

    # --- per frame -----------------------------------------------------------------------
    def on_tick(self, ctx: TickContext) -> None:
        self._focused = ctx.game_focused
        game = ctx.memory
        if game is None:          # not reading the real game (or left the world)
            self._blocker.uninstall()
            self._restore()
            return
        if self.val("keys") == WASD:
            self._blocker.install()
        else:
            self._blocker.uninstall()

        if self._start is None or self._start.player_addr != game.player_addr:
            body = game.read_player_body()
            if body is None:
                return
            self._game, self._start, self._offset = game, body, Vec3(0.0, 0.0, 0.0)

        player = ctx.state.player
        if ctx.game_focused:
            move, boost = self._input(player.yaw)
            length = move.length()
            if length > 0:
                speed = self.val("speed") * (4 if self.val("boost") and boost else 1)
                self._offset = self._offset + move * (speed * ctx.dt / length)

        body = self._start.moved(self._offset)
        game.write_player_body(body)   # every frame, so physics/gravity can't drift it
        player.pos = Vec3(body.pos.x, body.min.y, body.pos.z)   # keep this frame's overlay in sync
