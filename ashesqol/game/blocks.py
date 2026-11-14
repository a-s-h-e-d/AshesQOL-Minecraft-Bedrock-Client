"""Catalog of blocks offered in the BlockESP picker (any other id can be typed in by hand).

Ids are Bedrock block names without the 'minecraft:' prefix.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class BlockInfo:
    id: str
    group: str
    color: tuple[int, int, int, int]

    @property
    def full_id(self) -> str:
        return self.id if ":" in self.id else f"minecraft:{self.id}"

    @property
    def label(self) -> str:
        return self.id.split(":")[-1].replace("_", " ").title()


def _group(group, color, *ids):
    return [BlockInfo(i, group, color) for i in ids]


_GOLD, _ORANGE, _PURPLE = (255, 200, 60, 255), (255, 140, 40, 255), (190, 90, 255, 255)

CATALOG: list[BlockInfo] = [
    *_group("Storage", _ORANGE, "chest", "trapped_chest", "barrel", "hopper", "dispenser", "dropper",
            "crafter", "decorated_pot", "chiseled_bookshelf"),
    BlockInfo("ender_chest", "Storage", (40, 200, 160, 255)),
    *_group("Storage", _PURPLE, "undyed_shulker_box", "white_shulker_box", "black_shulker_box",
            "purple_shulker_box", "red_shulker_box", "blue_shulker_box", "green_shulker_box"),
    BlockInfo("mob_spawner", "Spawners", (255, 60, 60, 255)),
    BlockInfo("trial_spawner", "Spawners", (255, 90, 60, 255)),
    BlockInfo("vault", "Spawners", (255, 120, 60, 255)),
    BlockInfo("diamond_ore", "Ores", (80, 230, 255, 255)),
    BlockInfo("deepslate_diamond_ore", "Ores", (80, 230, 255, 255)),
    BlockInfo("ancient_debris", "Ores", (170, 100, 70, 255)),
    BlockInfo("emerald_ore", "Ores", (60, 230, 100, 255)),
    BlockInfo("deepslate_emerald_ore", "Ores", (60, 230, 100, 255)),
    *_group("Ores", _GOLD, "gold_ore", "deepslate_gold_ore", "nether_gold_ore"),
    *_group("Ores", (225, 190, 160, 255), "iron_ore", "deepslate_iron_ore"),
    *_group("Ores", (230, 120, 80, 255), "copper_ore", "deepslate_copper_ore"),
    *_group("Ores", (255, 40, 40, 255), "redstone_ore", "lit_redstone_ore", "deepslate_redstone_ore",
            "lit_deepslate_redstone_ore"),
    *_group("Ores", (50, 90, 230, 255), "lapis_ore", "deepslate_lapis_ore"),
    *_group("Ores", (60, 60, 60, 255), "coal_ore", "deepslate_coal_ore"),
    BlockInfo("quartz_ore", "Ores", (240, 235, 225, 255)),
    BlockInfo("budding_amethyst", "Ores", _PURPLE),
    *_group("Utility", (200, 200, 200, 255), "crafting_table", "furnace", "lit_furnace", "blast_furnace",
            "smoker", "anvil", "enchanting_table", "brewing_stand", "cartography_table", "smithing_table",
            "grindstone", "stonecutter_block", "loom", "lectern", "bed"),
    BlockInfo("beacon", "Utility", (120, 240, 255, 255)),
    BlockInfo("respawn_anchor", "Utility", _PURPLE),
    BlockInfo("end_portal_frame", "Structures", (120, 200, 120, 255)),
    BlockInfo("portal", "Structures", _PURPLE),
    BlockInfo("end_portal", "Structures", (30, 30, 60, 255)),
    *_group("Structures", (200, 170, 120, 255), "suspicious_sand", "suspicious_gravel"),
    *_group("Structures", (40, 120, 140, 255), "sculk_shrieker", "sculk_catalyst", "sculk_sensor"),
    BlockInfo("tnt", "Building", (255, 60, 60, 255)),
    *_group("Building", (110, 60, 160, 255), "obsidian", "crying_obsidian"),
    *_group("Building", (170, 130, 80, 255), "oak_planks", "spruce_planks", "birch_planks", "bookshelf"),
    *_group("Building", (150, 150, 150, 255), "cobblestone", "mossy_cobblestone", "stone", "bedrock"),
    BlockInfo("lava", "Fluids", (255, 120, 20, 255)),
    BlockInfo("water", "Fluids", (40, 100, 255, 255)),
]

BY_ID = {b.id: b for b in CATALOG}
DEFAULT_SELECTION = ["chest", "trapped_chest", "ender_chest", "barrel", "mob_spawner", "trial_spawner",
                     "diamond_ore", "deepslate_diamond_ore", "ancient_debris"]
DEFAULT_COLOR = (255, 255, 255, 255)


def short_id(block_id: str) -> str:
    """'minecraft:diamond_ore' -> 'diamond_ore' (other namespaces are kept)."""
    return block_id[len("minecraft:"):] if block_id.startswith("minecraft:") else block_id


def default_color(block_id: str) -> tuple[int, int, int, int]:
    info = BY_ID.get(short_id(block_id))
    return info.color if info else DEFAULT_COLOR
