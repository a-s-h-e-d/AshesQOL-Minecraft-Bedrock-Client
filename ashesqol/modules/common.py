"""Shared base for modules that draw something per entity (ESP, tracers, nametags)."""
from .base import Module
from .settings import BoolSetting, ColorSetting, SliderSetting

CATEGORIES = ("player", "hostile", "passive", "other")
_DEFAULT_COLORS = {
    "player": (90, 170, 255, 255),
    "hostile": (255, 85, 85, 255),
    "passive": (95, 225, 130, 255),
    "other": (210, 210, 210, 255),
}


class EntityModule(Module):
    default_range = 64

    def setup(self) -> None:
        self.add(BoolSetting("show_player", "Players", True))
        self.add(BoolSetting("show_hostile", "Hostile mobs", True))
        self.add(BoolSetting("show_passive", "Passive mobs", True))
        self.add(BoolSetting("show_other", "Other (items, etc.)", False))
        self.add(SliderSetting("range", "Range (blocks)", self.default_range, 4, 256, 1))
        for cat in CATEGORIES:
            self.add(ColorSetting(f"color_{cat}", f"{cat.capitalize()} color", _DEFAULT_COLORS[cat]))

    def targets(self, ctx):
        """Yield (entity, distance, QColor) for visible entities, farthest first."""
        state = ctx.state
        if not state.valid or state.player is None or ctx.camera is None:
            return
        origin = state.player.pos
        max_range = self.val("range")
        found = []
        for e in state.entities:
            cat = e.category
            if not self.val(f"show_{cat}"):
                continue
            dist = origin.distance(e.pos)
            if dist <= max_range:
                found.append((e, dist, self.settings[f"color_{cat}"].qcolor))
        found.sort(key=lambda item: item[1], reverse=True)
        yield from found
