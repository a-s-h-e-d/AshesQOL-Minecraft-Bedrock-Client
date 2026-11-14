ACCENT = "#ff7828"

STYLESHEET = f"""
QWidget {{
    background-color: #16161c;
    color: #e6e6e6;
    font-family: "Segoe UI";
    font-size: 10pt;
}}
QLabel#title {{ font-size: 16pt; font-weight: 700; color: {ACCENT}; }}
QLabel#moduleTitle {{ font-size: 13pt; font-weight: 600; }}
QLabel#muted, QLabel#status {{ color: #9a9aa6; }}
QGroupBox {{
    border: 1px solid #2c2c36; border-radius: 6px; margin-top: 10px; padding: 8px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #9a9aa6; }}
QListWidget {{
    background-color: #1c1c24; border: 1px solid #2c2c36; border-radius: 6px; padding: 4px;
}}
QListWidget::item {{ padding: 6px 4px; border-radius: 4px; }}
QListWidget::item:selected {{ background-color: #2a2a36; color: #ffffff; }}
QScrollArea {{ border: 1px solid #2c2c36; border-radius: 6px; }}
QPushButton {{
    background-color: #262630; border: 1px solid #34343f; border-radius: 4px; padding: 5px 12px;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton#power {{ font-weight: 600; color: #9a9aa6; }}
QPushButton#power:checked {{ background-color: {ACCENT}; border-color: {ACCENT}; color: #16161c; }}
QLineEdit {{
    background-color: #1f1f28; border: 1px solid #34343f; border-radius: 4px; padding: 5px 8px;
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QComboBox, QDoubleSpinBox {{
    background-color: #1f1f28; border: 1px solid #34343f; border-radius: 4px; padding: 3px 6px;
}}
QCheckBox::indicator, QListWidget::indicator {{
    width: 12px; height: 12px; border: 1px solid #55555f; border-radius: 3px; background: #1f1f28;
}}
QCheckBox::indicator:checked, QListWidget::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT};
}}
QSlider::groove:horizontal {{ height: 4px; background: #34343f; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {ACCENT}; width: 12px; margin: -5px 0; border-radius: 6px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSplitter::handle {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #3a3a46; border-radius: 3px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ height: 0; background: none; }}
"""
