"""Data sources that produce a GameState each frame.

MockProvider   - simulated world so the overlay can be built and tested without the game.
MemoryProvider - reads Minecraft's memory (see memory_provider.py).
"""
import math

from .math3d import Vec3
from .state import BlockHit, Entity, GameState, LocalPlayer

class DataProvider:
    key = ""
    label = ""
    wanted_blocks: frozenset[str] = frozenset()   # set by the app from enabled modules

    def poll(self, dt: float) -> GameState:
        raise NotImplementedError

# (type, name, orbit radius, angular speed rad/s, phase, y offset)
_MOCK_ENTITIES = [
    ("minecraft:player", "Steve", 12, 0.15, 0.0, 0),
    ("minecraft:zombie", "Zombie", 8, 0.25, 1.0, 0),
    ("minecraft:skeleton", "Skeleton", 18, -0.10, 2.0, 2),
    ("minecraft:creeper", "Creeper", 5, 0.35, 3.5, 0),
    ("minecraft:enderman", "Enderman", 30, 0.05, 4.8, 1),
    ("minecraft:cow", "Cow", 14, -0.20, 4.2, -1),
    ("minecraft:pig", "Pig", 25, 0.08, 5.6, 3),
    ("minecraft:item", "Diamond", 4, 0.00, 0.5, 0),
]
_SIZES = {  # width, height, max health
    "player": (0.6, 1.8, 20), "zombie": (0.6, 1.9, 20), "skeleton": (0.6, 1.99, 20),
    "creeper": (0.6, 1.7, 20), "enderman": (0.6, 2.9, 40), "cow": (0.9, 1.3, 10),
    "pig": (0.9, 0.9, 10), "item": (0.25, 0.25, None),
}

# A few demo blocks around the mock player: (x, y, z, id)
_MOCK_BLOCKS = [
    (6, 64, 3, "chest"), (7, 64, 3, "chest"), (-9, 63, 8, "barrel"), (3, 60, -7, "mob_spawner"),
    (-4, 52, -5, "diamond_ore"), (-5, 52, -5, "diamond_ore"), (-4, 51, -6, "deepslate_diamond_ore"),
    (12, 58, -10, "gold_ore"), (14, 30, 9, "ancient_debris"), (-15, 64, -2, "ender_chest"),
    (2, 64, 12, "crafting_table"), (9, 61, -14, "iron_ore"),
]


class MockProvider(DataProvider):
    key = "mock"
    label = "Mock (demo data)"

    def __init__(self):
        self.t = 0.0

    def poll(self, dt: float) -> GameState:
        self.t += dt
        t = self.t
        center = Vec3(0.5, 64.0, 0.5)
        yaw = ((t * 20.0) + 180) % 360 - 180
        player = LocalPlayer(pos=center, yaw=yaw, pitch=8 * math.sin(t * 0.4) + 5,
                             health=20, max_health=20)
        entities = []
        for uid, (type_id, name, radius, speed, phase, y_off) in enumerate(_MOCK_ENTITIES, start=1):
            angle = phase + speed * t
            w, h, max_hp = _SIZES[type_id.split(":")[1]]
            hp = None if max_hp is None else max(1, round(max_hp * (0.55 + 0.45 * math.sin(t * 0.3 + phase))))
            entities.append(Entity(
                uid=uid, type_id=type_id, name=name,
                pos=Vec3(center.x + radius * math.cos(angle), center.y + y_off, center.z + radius * math.sin(angle)),
                width=w, height=h, health=hp, max_health=max_hp,
            ))
        blocks = [BlockHit(int(center.x) + x, y, int(center.z) + z, b)
                  for x, y, z, b in _MOCK_BLOCKS if b in self.wanted_blocks]
        return GameState(valid=True, source=self.key, player=player, entities=entities, blocks=blocks)
