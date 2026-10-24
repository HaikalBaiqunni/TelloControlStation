"""
src/ui/widgets/compass_widget.py
Rotating compass rose widget — QPainter based.

Features:
  - Cardinal (N/E/S/W) and intercardinal tick marks
  - N highlighted in red, others in cyan
  - Heading bug arrow pinned to top
  - Center readout showing current heading in degrees
  - Circular clip + border ring
"""

import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import QWidget


C_BG       = QColor(0x0d, 0x15, 0x20)
C_BORDER   = QColor(0x00, 0xd4, 0xff, 0x55)
C_CARD     = QColor(0x00, 0xd4, 0xff)      # cardinal direction labels
C_NORTH    = QColor(0xff, 0x40, 0x40)      # N label red
C_TICK_MAJ = QColor(0x00, 0xd4, 0xff, 0xbb)
C_TICK_MIN = QColor(0x1e, 0x3d, 0x5a, 0xff)
C_BUG      = QColor(0x00, 0xd4, 0xff, 0xcc)
C_CENTER   = QColor(0x08, 0x14, 0x20)
C_HDG_TEXT = QColor(0x00, 0xd4, 0xff)


class CompassWidget(QWidget):
    """
    Compass rose widget.

    Update via:
        widget.set_heading(yaw_degrees)   # 0–360
    """

    def __init__(self, parent=None, size: int = 90):
        super().__init__(parent)
        self._heading = 0.0
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_heading(self, yaw: float):
        self._heading = yaw % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        W = self.width()
        H = self.height()
        cx, cy = W / 2.0, H / 2.0
        radius = min(cx, cy) - 2

        # Background circle
        painter.setBrush(QBrush(C_BG))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # ── Rotating tick marks and labels ────────────────────────────
        dirs = {0: 'N', 90: 'E', 180: 'S', 270: 'W'}

        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-self._heading)   # rotate so heading points to top

        for deg in range(0, 360, 5):
            angle_rad = math.radians(deg - 90)  # -90 so 0° is at top
            is_card  = deg % 90 == 0
            is_major = deg % 30 == 0

            tick_len = (radius * 0.18) if is_card else (radius * 0.10 if is_major else radius * 0.06)
            r_outer = radius - 1
            r_inner = r_outer - tick_len

            x1 = math.cos(angle_rad) * r_outer
            y1 = math.sin(angle_rad) * r_outer
            x2 = math.cos(angle_rad) * r_inner
            y2 = math.sin(angle_rad) * r_inner

            col = C_TICK_MAJ if (is_card or is_major) else C_TICK_MIN
            lw  = 1.5 if is_card else 1.0
            painter.setPen(QPen(col, lw))
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

            if deg in dirs:
                label = dirs[deg]
                lr = radius - tick_len - (radius * 0.14)
                lx = math.cos(angle_rad) * lr
                ly = math.sin(angle_rad) * lr
                font_size = max(8, int(radius * 0.18)) if is_card else max(7, int(radius * 0.13))
                font = QFont('Courier New', font_size)
                font.setBold(True)
                painter.setFont(font)
                color = C_NORTH if label == 'N' else C_CARD
                painter.setPen(QPen(color, 1))
                # Center the text manually
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(label)
                th = fm.height()
                painter.drawText(QPointF(lx - tw / 2, ly + th / 4), label)

        painter.restore()

        # ── Heading bug (fixed at top) ─────────────────────────────────
        bug = QPainterPath()
        bug.moveTo(cx, cy - radius + 2)
        bug.lineTo(cx - 4, cy - radius + 10)
        bug.lineTo(cx + 4, cy - radius + 10)
        bug.closeSubpath()
        painter.fillPath(bug, QBrush(C_BUG))

        # ── Center circle + heading readout ────────────────────────────
        center_r = radius * 0.28
        painter.setBrush(QBrush(C_CENTER))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), center_r, center_r)

        painter.setPen(QPen(C_HDG_TEXT, 1))
        font = QFont('Courier New', max(7, int(radius * 0.15)))
        font.setBold(True)
        painter.setFont(font)
        hdg_text = f'{int(self._heading):03d}°'
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(hdg_text)
        painter.drawText(QPointF(cx - tw / 2, cy + fm.height() / 4), hdg_text)

        # ── Border ring ────────────────────────────────────────────────
        painter.setPen(QPen(C_BORDER, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)
