"""
src/ui/widgets/vehicle_panel.py
VEHICLE glass card: battery ring, altitude and a grid of live telemetry cells.
"""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.drone.state_parser import DroneState
from src.ui import theme
from src.ui.widgets.glass import GlassPanel


class BatteryRing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(84, 84)
        self._v = -1

    def set_value(self, v: int):
        if v != self._v:
            self._v = v
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(8, 8, 68, 68)
        p.setPen(QPen(QColor(255, 255, 255, 24), 8))
        p.drawArc(r, 0, 360 * 16)
        if self._v >= 0:
            col = theme.ACCENT if self._v > 30 else (theme.WARN if self._v > 15 else theme.ALERT)
            p.setPen(QPen(col, 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(r, 90 * 16, -int(self._v / 100 * 360 * 16))
        p.setPen(QPen(theme.TEXT))
        p.setFont(QFont(theme.FONT_UI, 13, QFont.Weight.DemiBold))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"{self._v}%" if self._v >= 0 else "--")


class KvCell(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("kv")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(0)
        t = QLabel(title)
        t.setObjectName("muted")
        self.v = QLabel("--")
        self.v.setObjectName("kvv")
        lay.addWidget(t)
        lay.addWidget(self.v)


class VehiclePanel(GlassPanel):
    CELLS = [("speed", "SPEED cm/s"), ("temp", "TEMP °C"), ("pitch", "PITCH"), ("roll", "ROLL"),
             ("hdg", "HDG"), ("tof", "TOF cm"), ("baro", "BARO"), ("vz", "V-SPD cm/s")]

    def __init__(self, parent=None):
        super().__init__("Vehicle", "TELLO", parent)
        top = QHBoxLayout()
        self.ring = BatteryRing()
        top.addWidget(self.ring)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.alt = QLabel("--")
        self.alt.setObjectName("big")
        cap = QLabel("ALTITUDE cm")
        cap.setObjectName("muted")
        col.addStretch(1)
        col.addWidget(self.alt)
        col.addWidget(cap)
        col.addStretch(1)
        top.addLayout(col, 1)
        self.body.addLayout(top)

        grid = QGridLayout()
        grid.setSpacing(6)
        self._cells = {}
        for i, (key, title) in enumerate(self.CELLS):
            c = KvCell(title)
            self._cells[key] = c.v
            grid.addWidget(c, i // 2, i % 2)
        self.body.addLayout(grid)
        self.body.addStretch(1)

    def update_state(self, s: DroneState):
        self.ring.set_value(s.bat)
        self.alt.setText(str(s.h))
        c = self._cells
        c["speed"].setText(f"{s.ground_speed_cms:.0f}")
        c["temp"].setText(f"{s.temp_avg:.0f}")
        c["pitch"].setText(f"{s.pitch:+.0f}°")
        c["roll"].setText(f"{s.roll:+.0f}°")
        c["hdg"].setText(f"{int(s.yaw) % 360:03d}°")
        c["tof"].setText(str(s.tof))
        c["baro"].setText(f"{s.baro:.0f}")
        c["vz"].setText(f"{s.vgz:+.0f}")

    def clear_state(self):
        self.ring.set_value(-1)
        self.alt.setText("--")
        for v in self._cells.values():
            v.setText("--")
