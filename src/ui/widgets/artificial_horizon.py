"""
src/ui/widgets/artificial_horizon.py
Canvas-drawn Artificial Horizon (AHRS) widget — QPainter based.

Renders:
  - Rotating sky (dark blue) / ground (dark brown) split by pitch offset
  - Pitch ladder with degree labels
  - Roll arc scale at the rim
  - Fixed aircraft reference symbol (yellow chevron)
  - Roll indicator triangle that rotates with roll
  - Circular clip mask + border ring
"""

import math

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient,
)
from PySide6.QtWidgets import QWidget


# ── Color palette ─────────────────────────────────────────────────────
C_SKY       = QColor(0x1a, 0x3a, 0x5a)          # blue-grey sky
C_GROUND    = QColor(0x3a, 0x20, 0x10)          # dark earthy brown
C_HORIZON   = QColor(0xff, 0xff, 0xff, 0x99)    # semi-white horizon line
C_LADDER    = QColor(0xff, 0xff, 0xff, 0x88)    # pitch ladder ticks
C_LADDER_LBL= QColor(0xff, 0xff, 0xff, 0x99)
C_AIRCRAFT  = QColor(0xff, 0xdd, 0x00)          # yellow aircraft symbol
C_ROLL_ARC  = QColor(0x00, 0xd4, 0xff, 0x66)   # cyan roll arc
C_ROLL_TRI  = QColor(0xff, 0xdd, 0x00)
C_BORDER    = QColor(0x00, 0xd4, 0xff, 0x55)
C_BG        = QColor(0x0a, 0x10, 0x20)


class ArtificialHorizonWidget(QWidget):
    """
    Artificial Horizon widget.

    Set attitude via:
        widget.set_attitude(roll_deg, pitch_deg)
    """

    def __init__(self, parent=None, size: int = 140):
        super().__init__(parent)
        self._roll  = 0.0   # degrees, positive = right wing down
        self._pitch = 0.0   # degrees, positive = nose up

        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    # ── Public API ───────────────────────────────────────────────────

    def set_attitude(self, roll: float, pitch: float):
        self._roll  = roll
        self._pitch = pitch
        self.update()

    # ── Painting ─────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        W = self.width()
        H = self.height()
        cx, cy = W / 2, H / 2
        radius = min(cx, cy) - 2

        # ── 1. Clip to circle ────────────────────────────────────────
        clip_path = QPainterPath()
        clip_path.addEllipse(QPointF(cx, cy), radius, radius)
        painter.setClipPath(clip_path)

        # ── 2. Sky / Ground (roll + pitch) ───────────────────────────
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._roll)

        # pixels per degree of pitch (calibrated for the widget size)
        px_per_deg = radius / 35.0
        pitch_offset = self._pitch * px_per_deg

        sky_rect    = QRectF(-W, -H - pitch_offset, W * 2, H * 2)
        ground_rect = QRectF(-W, -pitch_offset,      W * 2, H * 2)

        painter.fillRect(sky_rect,    QBrush(C_SKY))
        painter.fillRect(ground_rect, QBrush(C_GROUND))

        # Horizon line
        pen = QPen(C_HORIZON, 1.5)
        painter.setPen(pen)
        painter.drawLine(QPointF(-W, -pitch_offset), QPointF(W, -pitch_offset))

        # ── 3. Pitch ladder ──────────────────────────────────────────
        for deg in range(-30, 35, 5):
            if deg == 0:
                continue
            y = -pitch_offset - deg * px_per_deg
            half_w = (radius * 0.45) if deg % 10 == 0 else (radius * 0.28)
            alpha = 0xaa if deg % 10 == 0 else 0x66
            lc = QColor(0xff, 0xff, 0xff, alpha)
            painter.setPen(QPen(lc, 1.0))
            painter.drawLine(QPointF(-half_w, y), QPointF(half_w, y))

            if deg % 10 == 0:
                font = QFont('Courier New', max(7, int(radius * 0.10)))
                painter.setFont(font)
                painter.setPen(QPen(C_LADDER_LBL, 1))
                painter.drawText(QPointF(half_w + 3, y + 4), str(deg))

        painter.restore()

        # ── 4. Roll arc (fixed) ──────────────────────────────────────
        arc_radius = radius - 6
        pen_arc = QPen(C_ROLL_ARC, 1.0)
        painter.setPen(pen_arc)
        rect_arc = QRectF(cx - arc_radius, cy - arc_radius,
                          arc_radius * 2, arc_radius * 2)
        # Draw arc from -135° to -45° (top half, left-to-right)
        # Qt angles: 0 = 3 o'clock, counterclockwise positive
        painter.drawArc(rect_arc, int(135 * 16), int(-90 * 16))

        # Roll scale ticks
        for deg in (-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60):
            angle_rad = math.radians(-90 + deg)
            is_major = abs(deg) % 30 == 0
            tick_len = arc_radius * (0.12 if is_major else 0.07)
            r_outer = arc_radius
            r_inner = arc_radius - tick_len
            x1 = cx + math.cos(angle_rad) * r_outer
            y1 = cy + math.sin(angle_rad) * r_outer
            x2 = cx + math.cos(angle_rad) * r_inner
            y2 = cy + math.sin(angle_rad) * r_inner
            painter.setPen(QPen(C_ROLL_ARC if is_major else QColor(0x00, 0xd4, 0xff, 0x44), 1))
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # ── 5. Roll indicator triangle (rotates with roll) ───────────
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._roll)
        tri_r = arc_radius - 8
        tri = QPainterPath()
        tri.moveTo(0, -tri_r)
        tri.lineTo(-5, -tri_r + 9)
        tri.lineTo(5,  -tri_r + 9)
        tri.closeSubpath()
        painter.fillPath(tri, QBrush(C_ROLL_TRI))
        painter.restore()

        # ── 6. Fixed aircraft symbol (always horizontal) ──────────────
        painter.setPen(QPen(C_AIRCRAFT, 2.5))
        arm = radius * 0.38
        gap = radius * 0.13
        # Left arm
        painter.drawLine(QPointF(cx - arm, cy), QPointF(cx - gap, cy))
        # Right arm
        painter.drawLine(QPointF(cx + gap, cy), QPointF(cx + arm, cy))
        # Center tick down
        painter.drawLine(QPointF(cx, cy), QPointF(cx, cy + radius * 0.12))
        # Center dot
        painter.setBrush(QBrush(C_AIRCRAFT))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), 3, 3)

        # ── 7. Border ring (above clip) ───────────────────────────────
        painter.setClipping(False)
        painter.setPen(QPen(C_BORDER, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)
