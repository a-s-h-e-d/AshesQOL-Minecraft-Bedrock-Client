"""Plain snapshot of everything the modules render. Providers fill it in every frame."""
from dataclasses import dataclass, field

from .math3d import Vec3

HOSTILE = {
    "zombie", "husk", "drowned", "zombie_villager", "skeleton", "stray", "bogged", "wither_skeleton",
    "zombie_villager_v2", "creeper", "spider", "cave_spider", "enderman", "endermite", "silverfish", "witch", "slime",
    "magma_cube", "blaze", "ghast", "phantom", "pillager", "vindicator", "evocation_illager",
    "ravager", "vex", "guardian", "elder_guardian", "shulker", "hoglin", "zoglin", "piglin_brute",
    "warden", "breeze", "creaking", "wither", "ender_dragon",
}
PASSIVE = {
    "cow", "pig", "sheep", "chicken", "horse", "donkey", "mule", "llama", "rabbit", "cat", "ocelot",
    "wolf", "fox", "parrot", "turtle", "panda", "bee", "goat", "frog", "axolotl", "camel", "sniffer",
    "armadillo", "mooshroom", "villager_v2", "wandering_trader", "iron_golem", "snow_golem",
    "squid", "glow_squid", "dolphin", "cod", "salmon", "pufferfish", "tropicalfish", "bat", "strider",
    "allay", "polar_bear", "piglin", "zombie_pigman",
}


@dataclass(slots=True)
class Entity:
    uid: int
    type_id: str             # e.g. "minecraft:zombie"
    name: str
    pos: Vec3                # feet position
    width: float = 0.6
    height: float = 1.8
    health: float | None = None
    max_health: float | None = None

    @property
    def short_type(self) -> str:
        return self.type_id.split(":", 1)[-1]

    @property
    def category(self) -> str:
        t = self.short_type
        if t == "player":
            return "player"
        if t in HOSTILE:
            return "hostile"
        if t in PASSIVE:
            return "passive"
        return "other"

    def aabb_corners(self) -> list[Vec3]:
        hw = self.width / 2
        p = self.pos
        return [Vec3(p.x + dx, p.y + dy, p.z + dz)
                for dx in (-hw, hw) for dy in (0.0, self.height) for dz in (-hw, hw)]


@dataclass(slots=True)
class LocalPlayer:
    pos: Vec3                # feet position
    yaw: float
    pitch: float
    health: float | None = None
    max_health: float | None = None
    dimension: str = "overworld"   # overworld | nether | the_end
    eye_height: float = 1.62

    @property
    def eye_pos(self) -> Vec3:
        return Vec3(self.pos.x, self.pos.y + self.eye_height, self.pos.z)


@dataclass(slots=True, frozen=True)
class BlockHit:
    x: int
    y: int
    z: int
    block: str               # short id, e.g. "diamond_ore"


@dataclass(slots=True)
class GameState:
    valid: bool
    source: str = ""
    reason: str = ""                 # why data is missing when valid is False
    player: LocalPlayer | None = None
    entities: list[Entity] = field(default_factory=list)
    fov: float | None = None         # None = use the configured FOV
    blocks: list[BlockHit] = field(default_factory=list)   # only the block types modules asked for
    block_status: str = ""           # why blocks may be missing (e.g. "searching...")
    notices: list[tuple[str, str]] = field(default_factory=list)   # (kind, text): "entities" / "blocks"

    @classmethod
    def invalid(cls, reason: str, source: str = "") -> "GameState":
        return cls(valid=False, source=source, reason=reason)
