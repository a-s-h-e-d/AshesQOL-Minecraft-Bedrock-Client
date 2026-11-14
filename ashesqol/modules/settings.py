"""Typed module settings. The control window builds its widgets from these automatically."""
from PyQt6.QtGui import QColor


class Setting:
    def __init__(self, key: str, label: str, default, tooltip: str = ""):
        self.key = key
        self.label = label
        self.default = default
        self.tooltip = tooltip
        self.value = default

    def coerce(self, value):
        return value

    def set(self, value) -> None:
        self.value = self.coerce(value)

    def to_json(self):
        return self.value

    def load(self, raw) -> None:
        try:
            self.set(raw)
        except (TypeError, ValueError):
            self.value = self.default


class BoolSetting(Setting):
    def coerce(self, value):
        if not isinstance(value, bool):
            raise TypeError("expected bool")
        return value


class SliderSetting(Setting):
    def __init__(self, key, label, default, minimum, maximum, step=1.0, tooltip=""):
        super().__init__(key, label, default, tooltip)
        self.minimum, self.maximum, self.step = minimum, maximum, step

    @property
    def decimals(self) -> int:
        return 0 if self.step >= 1 else len(str(self.step).split(".")[1])

    def coerce(self, value):
        return min(self.maximum, max(self.minimum, float(value)))


class ChoiceSetting(Setting):
    def __init__(self, key, label, default, options, tooltip=""):
        super().__init__(key, label, default, tooltip)
        self.options = list(options)

    def coerce(self, value):
        if value not in self.options:
            raise ValueError(f"unknown option {value!r}")
        return value


class BlockListSetting(Setting):
    """Selected block ids (short form, e.g. 'diamond_ore') -> RGBA color."""

    def coerce(self, value):
        if not isinstance(value, dict):
            raise TypeError("expected {block_id: color}")
        out = {}
        for block_id, color in value.items():
            r, g, b, a = (max(0, min(255, int(c))) for c in color)
            out[str(block_id)] = (r, g, b, a)
        return out

    def to_json(self):
        return {k: list(v) for k, v in self.value.items()}


class ColorSetting(Setting):
    """RGBA tuple, 0-255 each."""

    def coerce(self, value):
        r, g, b, a = (int(c) for c in value)
        return tuple(max(0, min(255, c)) for c in (r, g, b, a))

    def to_json(self):
        return list(self.value)

    @property
    def qcolor(self) -> QColor:
        return QColor(*self.value)
