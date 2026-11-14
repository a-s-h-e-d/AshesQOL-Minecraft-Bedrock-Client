"""The separate control window: data source, general options, module list and settings."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QMainWindow, QPushButton, QScrollArea, QSlider,
    QSplitter, QVBoxLayout, QWidget,
)

from .. import APP_NAME, __version__
from ..modules.settings import BlockListSetting, BoolSetting, ChoiceSetting, ColorSetting, SliderSetting
from .block_picker import BlockPickerDialog
from .keys import key_name, pretty

class ConfigKey:
    """Adapter so KeybindButton can edit a key stored in the app config."""

    def __init__(self, config, key: str, allow_none: bool = False):
        self.config, self.key, self.allow_none = config, key, allow_none

    @property
    def keybind(self):
        return self.config[self.key]

    @keybind.setter
    def keybind(self, value):
        if value or self.allow_none:
            self.config[self.key] = value


class KeybindButton(QPushButton):
    """Click, then press a key. Works for modules and for ConfigKey targets."""

    def __init__(self, target, on_change, prefix: str = "Keybind"):
        super().__init__()
        self.target = target
        self.on_change = on_change
        self.prefix = prefix
        self.listening = False
        self.clicked.connect(self._start)
        self._refresh()

    def _refresh(self):
        if self.listening:
            self.setText("Press a key... (Esc clears)")
        else:
            self.setText(f"{self.prefix}: {pretty(self.target.keybind)}")

    def _start(self):
        self.listening = True
        self._refresh()
        self.grabKeyboard()

    def keyPressEvent(self, event):
        if not self.listening:
            return super().keyPressEvent(event)
        if event.key() == Qt.Key.Key_Escape.value:
            self.target.keybind = None
        else:
            name = key_name(event)
            if name is None:
                return  # unsupported key; keep listening
            self.target.keybind = name
        self.listening = False
        self.releaseKeyboard()
        self._refresh()
        self.on_change()


def _setting_widget(setting, on_change) -> QWidget:
    if isinstance(setting, BoolSetting):
        w = QCheckBox()
        w.setChecked(setting.value)
        w.toggled.connect(lambda v: (setting.set(v), on_change()))
        return w

    if isinstance(setting, ChoiceSetting):
        w = QComboBox()
        w.addItems(setting.options)
        w.setCurrentText(setting.value)
        w.currentTextChanged.connect(lambda v: (setting.set(v), on_change()))
        return w

    if isinstance(setting, SliderSetting):
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        slider = QSlider(Qt.Orientation.Horizontal)
        steps = round((setting.maximum - setting.minimum) / setting.step)
        slider.setRange(0, steps)
        slider.setValue(round((setting.value - setting.minimum) / setting.step))
        label = QLabel()
        label.setMinimumWidth(40)

        def update(pos):
            setting.set(setting.minimum + pos * setting.step)
            label.setText(f"{setting.value:.{setting.decimals}f}")
            on_change()

        slider.valueChanged.connect(update)
        label.setText(f"{setting.value:.{setting.decimals}f}")
        row.addWidget(slider, 1)
        row.addWidget(label)
        return box

    if isinstance(setting, ColorSetting):
        w = QPushButton()
        w.setFixedWidth(70)

        def paint():
            r, g, b, a = setting.value
            w.setStyleSheet(f"background-color: rgba({r},{g},{b},{a}); border: 1px solid #555;")

        def pick():
            color = QColorDialog.getColor(setting.qcolor, w, setting.label,
                                          QColorDialog.ColorDialogOption.ShowAlphaChannel)
            if color.isValid():
                setting.set(color.getRgb())
                paint()
                on_change()

        w.clicked.connect(pick)
        paint()
        return w

    if isinstance(setting, BlockListSetting):
        w = QPushButton()

        def label():
            w.setText(f"Choose blocks... ({len(setting.value)} selected)")

        def open_picker():
            dialog = BlockPickerDialog(setting.value, w.window())
            if dialog.exec():
                setting.set(dialog.selection())
                label()
                on_change()

        w.clicked.connect(open_picker)
        label()
        return w

    return QLabel(repr(setting.value))


class ControlWindow(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(780, 560)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 12)

        header = QHBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        self.status = QLabel()
        self.status.setObjectName("status")
        header.addWidget(self.status)
        self.power = QPushButton()
        self.power.setObjectName("power")
        self.power.setCheckable(True)
        self.power.setMinimumWidth(110)
        self.power.setToolTip(f"Turn all of AshesQOL on/off (hotkey: {app.config['toggle_key']})")
        self.power.clicked.connect(lambda checked: self.app.set_active(checked))
        header.addSpacing(10)
        header.addWidget(self.power)
        root.addLayout(header)
        self.sync_active()

        root.addWidget(self._build_general())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.module_list = QListWidget()
        self.module_list.setMaximumWidth(220)
        for module in app.modules:
            item = QListWidgetItem(module.name)
            if module.toggleable:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if module.enabled else Qt.CheckState.Unchecked)
            item.setToolTip(module.description)
            self.module_list.addItem(item)
        self.module_list.itemChanged.connect(self._on_item_changed)
        self.module_list.currentRowChanged.connect(self._show_module)
        splitter.addWidget(self.module_list)

        self.settings_area = QScrollArea()
        self.settings_area.setWidgetResizable(True)
        splitter.addWidget(self.settings_area)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        footer = QHBoxLayout()
        self.hint = QLabel()
        self.hint.setObjectName("muted")
        footer.addWidget(self.hint)
        footer.addStretch()
        save = QPushButton("Save")
        save.clicked.connect(app.save)
        footer.addWidget(save)
        root.addLayout(footer)

        self.setCentralWidget(central)
        self.module_list.setCurrentRow(0)
        self._update_hint()

    def _update_hint(self):
        cfg = self.app.config
        self.hint.setText(f"{pretty(cfg['clickgui_key'])}: click GUI  ·  {pretty(cfg['menu_key'])}: this window  ·  "
                          f"{pretty(cfg['toggle_key'])}: on/off  ·  keybinds work while Minecraft is focused")
        self.power.setToolTip(f"Turn all of AshesQOL on/off (hotkey: {pretty(cfg['toggle_key'])})")

    def _build_general(self) -> QGroupBox:
        group = QGroupBox("General")
        form = QFormLayout(group)
        cfg = self.app.config

        source = QComboBox()
        for provider in self.app.providers.values():
            source.addItem(provider.label, provider.key)
        source.setCurrentIndex(max(0, source.findData(cfg["source"])))
        source.currentIndexChanged.connect(lambda _: self.app.set_source(source.currentData()))
        form.addRow("Data source", source)

        fov = QDoubleSpinBox()
        fov.setRange(30, 120)
        fov.setDecimals(0)
        fov.setValue(cfg["fov"])
        fov.setToolTip("Set this to the FOV in Minecraft's video settings so boxes line up")
        fov.valueChanged.connect(lambda v: cfg.__setitem__("fov", v))
        form.addRow("Game FOV", fov)

        keys = QHBoxLayout()
        keys.addWidget(KeybindButton(ConfigKey(cfg, "clickgui_key"), self._update_hint, "Click GUI"))
        keys.addWidget(KeybindButton(ConfigKey(cfg, "menu_key"), self._update_hint, "This window"))
        keys.addWidget(KeybindButton(ConfigKey(cfg, "toggle_key"), self._update_hint, "On/off"))
        form.addRow("Hotkeys", keys)

        for key, label in (("show_control_on_start", "Show this window when AshesQOL starts (else use the click GUI)"),
                           ("interpolate", "Smooth movement between game ticks (fixes laggy ESP trails)"),
                           ("only_when_focused", "Only show overlay while Minecraft is focused"),
                           ("preview_background", "Dim the preview area when the game isn't found")):
            box = QCheckBox(label)
            box.setChecked(cfg[key])
            box.toggled.connect(lambda v, k=key: cfg.__setitem__(k, v))
            form.addRow("", box)
        return group

    def _on_item_changed(self, item: QListWidgetItem):
        module = self.app.modules[self.module_list.row(item)]
        if module.toggleable:
            module.set_enabled(item.checkState() == Qt.CheckState.Checked)

    def _show_module(self, row: int):
        if row < 0:
            return
        module = self.app.modules[row]
        panel = QWidget()
        layout = QVBoxLayout(panel)
        title = QLabel(module.name)
        title.setObjectName("moduleTitle")
        layout.addWidget(title)
        desc = QLabel(module.description)
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addWidget(KeybindButton(module, lambda: None))

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        for setting in module.settings.values():
            widget = _setting_widget(setting, lambda: None)
            if setting.tooltip:
                widget.setToolTip(setting.tooltip)
            form.addRow(setting.label, widget)
        layout.addLayout(form)
        layout.addStretch()
        self.settings_area.setWidget(panel)

    def refresh_current(self):
        """Rebuild the visible settings panel (values may have changed in the click GUI)."""
        row = self.module_list.currentRow()
        if row >= 0 and self.isVisible():
            self._show_module(row)

    def sync_modules(self):
        """Refresh checkboxes after modules were toggled elsewhere (e.g. keybinds)."""
        self.module_list.blockSignals(True)
        for i, module in enumerate(self.app.modules):
            if module.toggleable:
                state = Qt.CheckState.Checked if module.enabled else Qt.CheckState.Unchecked
                self.module_list.item(i).setCheckState(state)
        self.module_list.blockSignals(False)

    def set_status(self, text: str):
        self.status.setText(text if self.app.active else f"DISABLED  ·  {text}")

    def sync_active(self):
        active = self.app.active
        self.power.setChecked(active)
        self.power.setText("●  Enabled" if active else "○  Disabled")

    def toggle_visible(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def closeEvent(self, event):
        self.app.quit()
        event.accept()
