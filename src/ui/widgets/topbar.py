"""
src/ui/widgets/topbar.py
Glass top bar with the page tabs and status chips. Each page owns one instance;
MainWindow keeps them in sync.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QWidget

from src.ui import theme
from src.ui.widgets.glass import GlassPanel

TABS = ["FLIGHT DATA", "FLIGHT PLAN", "LOGS"]


class TopBar(GlassPanel):
    tab_changed = Signal(int)

    def __init__(self, current: int, parent=None):
        super().__init__("", "", parent)
        self.setFixedHeight(46)
        self.body.setContentsMargins(14, 0, 14, 0)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.body.addLayout(row)

        logo = QLabel("TELLO  CS")
        logo.setObjectName("logo")
        row.addWidget(logo)
        row.addSpacing(10)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._tabs = []
        for i, name in enumerate(TABS):
            b = QPushButton(name)
            b.setObjectName("tab")
            b.setCheckable(True)
            b.setChecked(i == current)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self._group.addButton(b, i)
            self._tabs.append(b)
            row.addWidget(b)
        self._group.idClicked.connect(self.tab_changed)
        row.addStretch(1)

        self.right = row            # pages can append widgets via add_right()
        self._chip_link = self._chip("LINK OFFLINE")
        self._chip_mode = self._chip("MODE STANDBY")
        self._chip_pad = self._chip("KEYBOARD PILOT")
        self._chip_mis = self._chip("MISSION IDLE")
        for c in (self._chip_link, self._chip_mode, self._chip_pad, self._chip_mis):
            row.addWidget(c)
        self.set_link(False)

    def _chip(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setObjectName("chip")
        return l

    def _color(self, label: QLabel, color):
        label.setStyleSheet(
            f"color: {color.name()}; border-color: rgba({color.red()},{color.green()},{color.blue()},110);")

    def add_right(self, widget: QWidget):
        self.right.addWidget(widget)

    def set_tab(self, i: int):
        b = self._group.button(i)
        if b and not b.isChecked():
            b.setChecked(True)

    def set_link(self, online: bool):
        self._chip_link.setText("● LINK OK" if online else "○ LINK OFFLINE")
        self._color(self._chip_link, theme.OK if online else theme.MUTED)

    def set_mode(self, mode: str):
        self._chip_mode.setText(f"MODE {mode}")
        hot = mode in ("AIRBORNE", "AUTO MISSION")
        self._color(self._chip_mode, theme.OK if hot else theme.ALERT if mode == "E-STOP" else theme.TEXT)

    def set_pad(self, text: str, active: bool):
        self._chip_pad.setText(text)
        self._color(self._chip_pad, theme.ACCENT if active else theme.MUTED)

    def set_mission(self, text: str, running: bool):
        self._chip_mis.setText(text)
        self._color(self._chip_mis, theme.OK if running else theme.MUTED)
