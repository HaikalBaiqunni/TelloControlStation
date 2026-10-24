"""
src/ui/widgets/hud_telemetry.py
Semi-transparent HUD telemetry overlay panels.

Provides two overlay widgets:
  - TopCenterStatus  : mode tag + clock
  - BottomLeftTelemetry: altitude, speed, yaw, battery, roll, pitch, temp
"""

from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout


# ── Shared style constants ─────────────────────────────────────────────
FONT_MONO   = QFont('Courier New', 11)
FONT_MONO_S = QFont('Courier New', 10)
FONT_MONO_B = QFont('Courier New', 11)

C_BG       = QColor(0x00, 0x00, 0x00, 0xb0)   # semi-transparent black
C_BORDER   = QColor(0x00, 0xd4, 0xff, 0x33)
C_CYAN     = QColor(0x00, 0xd4, 0xff)
C_MUTED    = QColor(0x3a, 0x5a, 0x7a)
C_GREEN    = QColor(0x00, 0xff, 0x88)
C_AMBER    = QColor(0xff, 0x8c, 0x00)
C_RED      = QColor(0xff, 0x20, 0x20)


def _bat_color(pct: int) -> QColor:
    if pct > 50:  return C_GREEN
    if pct > 20:  return C_AMBER
    return C_RED


class _HudPanel(QWidget):
    """Base class: semi-transparent background panel with a thin border."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(C_BG))
        painter.setPen(QPen(C_BORDER, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))


class TopCenterStatus(_HudPanel):
    """
    Top-center HUD bar: flight mode + clock.
    Update via set_mode(mode_str) and set_connected(bool).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode      = 'STANDBY'
        self._mode_color = C_AMBER
        self._clock_str = '--:--:--'

        # Clock tick
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()

    def set_mode(self, mode: str, color: QColor = None):
        self._mode = mode
        self._mode_color = color or C_AMBER
        self.update()

    def _tick(self):
        self._clock_str = datetime.now().strftime('%H:%M:%S')
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        W, H = self.width(), self.height()
        cy = H / 2

        # Mode text (left-ish)
        painter.setFont(QFont('Courier New', 10, QFont.Weight.Bold))
        painter.setPen(QPen(self._mode_color, 1))
        painter.drawText(10, int(cy + 5), self._mode)

        # Clock (right-ish)
        painter.setFont(QFont('Courier New', 10))
        painter.setPen(QPen(C_MUTED, 1))
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(self._clock_str)
        painter.drawText(W - tw - 10, int(cy + 5), self._clock_str)

        # Center separator dots
        painter.setPen(QPen(C_MUTED, 1))
        painter.setFont(QFont('Courier New', 9))
        center_txt = '· TELLO CS ·'
        ctw = painter.fontMetrics().horizontalAdvance(center_txt)
        painter.drawText(int(W / 2 - ctw / 2), int(cy + 5), center_txt)


class BottomLeftTelemetry(_HudPanel):
    """
    Bottom-left HUD panel showing key telemetry values.
    Update via update_state(DroneState).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fields = {
            'ALT':   ('0',    'cm',    C_CYAN),
            'SPD':   ('0',    'cm/s',  C_CYAN),
            'YAW':   ('0°',   '',      C_CYAN),
            'BAT':   ('--',   '%',     C_GREEN),
            'ROLL':  ('0.0°', '',      C_CYAN),
            'PITCH': ('0.0°', '',      C_CYAN),
            'TEMP':  ('--',   '°C',    C_AMBER),
            'TOF':   ('--',   'cm',    C_MUTED),
        }

    def update_state(self, state):
        """Accept a DroneState object and refresh display."""
        bat = state.bat
        self._fields['ALT']   = (str(state.h),                    'cm',    C_CYAN)
        self._fields['SPD']   = (f'{state.ground_speed_cms:.0f}', 'cm/s',  C_CYAN)
        self._fields['YAW']   = (f'{state.yaw:.0f}°',             '',      C_CYAN)
        self._fields['BAT']   = (str(bat),                         '%',     _bat_color(bat))
        self._fields['ROLL']  = (f'{state.roll:.1f}°',             '',      C_CYAN)
        self._fields['PITCH'] = (f'{state.pitch:.1f}°',            '',      C_CYAN)
        self._fields['TEMP']  = (f'{state.temp_avg:.0f}',          '°C',    C_AMBER)
        self._fields['TOF']   = (str(state.tof),                   'cm',    C_MUTED)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        PAD_X, PAD_Y = 10, 8
        ROW_H = 20
        COL_W = 100   # width per field pair (label + value)

        # Layout: 2 columns of 4 rows
        items = list(self._fields.items())
        for i, (label, (value, unit, color)) in enumerate(items):
            col = i % 2
            row = i // 2
            x = PAD_X + col * COL_W
            y = PAD_Y + row * ROW_H

            # Label (muted)
            painter.setFont(QFont('Courier New', 9))
            painter.setPen(QPen(C_MUTED, 1))
            painter.drawText(x, y + ROW_H - 6, label + ':')

            # Value (colored)
            painter.setFont(QFont('Courier New', 11, QFont.Weight.Bold))
            painter.setPen(QPen(color, 1))
            val_txt = value + (' ' + unit if unit else '')
            lw = painter.fontMetrics().horizontalAdvance(label + ': ')
            painter.drawText(x + lw, y + ROW_H - 5, val_txt)
