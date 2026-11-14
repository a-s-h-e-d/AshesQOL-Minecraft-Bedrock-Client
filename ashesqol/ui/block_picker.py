"""Dialog for choosing which blocks BlockESP highlights, and their colors."""
import re

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QColorDialog, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout,
)

from ..game.blocks import CATALOG, BY_ID, default_color, short_id

_ID_ROLE = Qt.ItemDataRole.UserRole
_VALID_ID = re.compile(r"^([a-z0-9_.-]+:)?[a-z0-9_./-]+$")


def _swatch(color) -> QIcon:
    pix = QPixmap(14, 14)
    pix.fill(QColor(*color))
    return QIcon(pix)


class BlockPickerDialog(QDialog):
    def __init__(self, selected: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BlockESP blocks")
        self.resize(420, 560)
        self.colors = {b.id: b.color for b in CATALOG}
        self.colors.update(selected)
        self.checked = set(selected)

        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search, or type a block id (e.g. sea_lantern) and press Enter to add")
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._add_custom)
        layout.addWidget(self.search)

        self.list = QListWidget()
        self.list.itemChanged.connect(self._on_item_changed)
        self.list.itemDoubleClicked.connect(self._pick_color)
        layout.addWidget(self.list, 1)

        hint = QLabel("Tick blocks to highlight · double-click to change a color")
        hint.setObjectName("muted")
        layout.addWidget(hint)

        row = QHBoxLayout()
        clear = QPushButton("Clear all")
        clear.clicked.connect(self._clear)
        row.addWidget(clear)
        row.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        layout.addLayout(row)
        self._populate()

    def _ids(self) -> list[str]:
        custom = sorted(i for i in self.checked if i not in BY_ID)
        return custom + [b.id for b in CATALOG]

    def _populate(self) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for block_id in self._ids():
            info = BY_ID.get(block_id)
            text = f"{info.label}    ({info.group})" if info else f"{block_id}    (custom)"
            item = QListWidgetItem(_swatch(self.colors.get(block_id, default_color(block_id))), text)
            item.setData(_ID_ROLE, block_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if block_id in self.checked else Qt.CheckState.Unchecked)
            item.setToolTip(f"minecraft:{block_id}" if ":" not in block_id else block_id)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._filter(self.search.text())

    def _filter(self, text: str) -> None:
        needle = text.strip().lower().replace(" ", "_")
        for i in range(self.list.count()):
            item = self.list.item(i)
            block_id = item.data(_ID_ROLE)
            item.setHidden(bool(needle) and needle not in block_id and needle not in item.text().lower())

    def _add_custom(self) -> None:
        block_id = short_id(self.search.text().strip().lower().replace(" ", "_"))
        if not block_id or not _VALID_ID.match(block_id):
            return
        self.checked.add(block_id)
        self.colors.setdefault(block_id, default_color(block_id))
        self.search.clear()
        self._populate()

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        block_id = item.data(_ID_ROLE)
        if item.checkState() == Qt.CheckState.Checked:
            self.checked.add(block_id)
        else:
            self.checked.discard(block_id)

    def _pick_color(self, item: QListWidgetItem) -> None:
        block_id = item.data(_ID_ROLE)
        color = QColorDialog.getColor(QColor(*self.colors.get(block_id, default_color(block_id))), self,
                                      f"Color for {block_id}", QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            self.colors[block_id] = color.getRgb()
            item.setIcon(_swatch(self.colors[block_id]))

    def _clear(self) -> None:
        self.checked.clear()
        self._populate()

    def selection(self) -> dict:
        return {b: self.colors.get(b, default_color(b)) for b in sorted(self.checked)}
