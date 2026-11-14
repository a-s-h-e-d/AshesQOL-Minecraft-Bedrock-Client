"""Memory offsets, kept in data/offsets.json so game updates only touch that file."""
import json
from pathlib import Path

OFFSETS_PATH = Path(__file__).resolve().parent.parent / "data" / "offsets.json"


def _hex(value) -> int:
    return int(value, 16) if isinstance(value, str) else int(value)


class Offsets:
    def __init__(self, data: dict):
        self.data = data

    @classmethod
    def load(cls) -> "Offsets":
        try:
            return cls(json.loads(OFFSETS_PATH.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return cls({})

    @property
    def game_version(self) -> str:
        return self.data.get("game_version") or ""

    @property
    def exe_version(self) -> str:
        """Exact Minecraft.Windows.exe file version the offsets were found on (e.g. '1.26.63.1')."""
        return self.data.get("exe_version") or ""

    def supports(self, version: str | None) -> bool:
        return not self.exe_version or not version or version == self.exe_version

    @property
    def ready(self) -> bool:
        lp = self.data.get("local_player") or {}
        return bool(self.game_version and lp.get("vtable"))

    def arena(self, section: str) -> tuple[int, int] | None:
        """(align, offset) of an object at a fixed offset inside aligned heap segments."""
        arena = (self.data.get(section) or {}).get("arena")
        return (_hex(arena["align"]), _hex(arena["offset"])) if arena else None

    def get(self, section: str, key: str) -> int:
        """Numeric offset, e.g. get('actor', 'rotation')."""
        return _hex(self.data[section][key])

    def vtables(self, section: str) -> list[int]:
        """All accepted vtable RVAs (e.g. the local player's class differs on servers)."""
        value = self.data[section]["vtable"]
        return [_hex(v) for v in value] if isinstance(value, list) else [_hex(value)]

    def vtable(self, section: str) -> int:
        return self.vtables(section)[0]

    def chains(self, section: str) -> list[list[int]]:
        return [[_hex(v) for v in chain] for chain in (self.data.get(section) or {}).get("chains", [])]

    @property
    def has_entities(self) -> bool:
        return bool((self.data.get("actor_storage") or {}).get("vtable"))
