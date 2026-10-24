"""
src/ui/widgets/fighter_hud.py
Modern Ace Combat / F-35 Fighter Jet HUD overlay widget.

Typography: Bahnschrift (DIN 1451 modern aerospace standard)
Palette: Fluorescent military emerald green (#55ff99) with vector glow.
"""

import math
from typing import Optional

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import QWidget


HUD_GREEN     = QColor(0x55, 0xff, 0x99)          # Primary fluorescent vector green
HUD_GREEN_GLO = QColor(0x55, 0xff, 0x99, 0x44)    # Glow / transparency
HUD_GREEN_DIM = QColor(0x30, 0xaa, 0x60, 0x99)    # Minor ticks
HUD_ALERT     = QColor(0xff, 0x33, 0x44)          # Alert red
HUD_AMBER     = QColor(0xff, 0xb0, 0x20)          # Caution amber


class FighterHUDWidget(QWidget):
    """
    Transparent vector HUD drawn directly over the camera feed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self._roll: float  = 0.0
        self._pitch: float = 0.0
        self._yaw: float   = 0.0
        self._alt: float   = 0.0
        self._speed: float = 0.0
        self._tof: float   = 0.0
        self._msg: str     = "ALL SENSORS NOMINAL"

    def update_telemetry(self, roll: float, pitch: float, yaw: float, alt: float, speed: float, tof: float = 0.0):
        self._roll  = roll
        self._pitch = pitch
        self._yaw   = yaw % 360
        self._alt   = alt
        self._speed = speed
        self._tof   = tof
        self.update()

    def set_radio_message(self, msg: str):
        self._msg = msg
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        W = float(self.width())
        H = float(self.height())
        cx = W / 2.0
        cy = H / 2.0

        # 1. Center Watermark Reticle (-\v/-)
        self._draw_aircraft_watermark(painter, cx, cy)

        # 2. Dynamic Rotating & Shifting Pitch Ladder
        self._draw_pitch_ladder(painter, cx, cy, H)

        # 3. Left Speed Ladder Tape
        self._draw_speed_ladder(painter, cx, cy, H)

        # 4. Right Altitude Ladder Tape
        self._draw_altitude_ladder(painter, cx, cy, H)

        # 5. Top Heading Ribbon Tape
        self._draw_heading_tape(painter, cx, W)

        # 6. Military Tactical Transmission Banner
        self._draw_radio_banner(painter, cx)

    def _draw_aircraft_watermark(self, p: QPainter, cx: float, cy: float):
        p.setPen(QPen(HUD_GREEN, 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)

        r = 9.0
        p.drawEllipse(QPointF(cx, cy), r, r)

        p.drawLine(QPointF(cx - 5, cy - 2), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx, cy + 4),     QPointF(cx + 5, cy - 2))

        p.drawLine(QPointF(cx - 28, cy), QPointF(cx - r, cy))
        p.drawLine(QPointF(cx + r, cy),  QPointF(cx + 28, cy))

    def _draw_pitch_ladder(self, p: QPainter, cx: float, cy: float, H: float):
        p.save()
        p.translate(cx, cy)
        p.rotate(-self._roll)

        px_per_deg = H / 48.0
        pitch_shift = self._pitch * px_per_deg

        bar_width = 80.0
        gap_width = 34.0

        for deg in range(-30, 35, 5):
            if deg == 0:
                continue

            y = -pitch_shift - (deg * px_per_deg)
            if abs(y) > H * 0.38:
                continue

            is_positive = deg > 0
            is_major    = deg % 10 == 0

            bw = bar_width if is_major else bar_width * 0.72
            tick_len = 6.0

            if is_positive:
                p.setPen(QPen(HUD_GREEN, 1.6))
                p.drawLine(QPointF(-bw, y), QPointF(-gap_width, y))
                p.drawLine(QPointF(-bw, y), QPointF(-bw, y + tick_len))
                p.drawLine(QPointF(gap_width, y), QPointF(bw, y))
                p.drawLine(QPointF(bw, y), QPointF(bw, y + tick_len))
            else:
                pen_dashed = QPen(HUD_GREEN, 1.4, Qt.PenStyle.DashLine)
                p.setPen(pen_dashed)
                p.drawLine(QPointF(-bw, y), QPointF(-gap_width, y))
                p.drawLine(QPointF(-bw, y), QPointF(-bw, y - tick_len))
                p.drawLine(QPointF(gap_width, y), QPointF(bw, y))
                p.drawLine(QPointF(bw, y), QPointF(bw, y - tick_len))

            p.setPen(QPen(HUD_GREEN, 1))
            p.setFont(QFont("Bahnschrift", 9, QFont.Weight.DemiBold))
            lbl = str(abs(deg))
            p.drawText(QPointF(-bw - 20, y + 4), lbl)
            p.drawText(QPointF(bw + 6, y + 4), lbl)

        # Zero horizon dashed line
        y0 = -pitch_shift
        p.setPen(QPen(HUD_GREEN_DIM, 1.0, Qt.PenStyle.DashDotLine))
        p.drawLine(QPointF(-bar_width * 1.5, y0), QPointF(-gap_width, y0))
        p.drawLine(QPointF(gap_width, y0),        QPointF(bar_width * 1.5, y0))

        p.restore()

    def _draw_speed_ladder(self, p: QPainter, cx: float, cy: float, H: float):
        ladder_x = cx - 195.0
        tape_h   = 170.0

        p.setPen(QPen(HUD_GREEN, 1.6))
        p.drawLine(QPointF(ladder_x, cy - tape_h / 2), QPointF(ladder_x, cy + tape_h / 2))
        p.drawLine(QPointF(ladder_x, cy - tape_h / 2), QPointF(ladder_x + 8, cy - tape_h / 2))
        p.drawLine(QPointF(ladder_x, cy + tape_h / 2), QPointF(ladder_x + 8, cy + tape_h / 2))

        p.setPen(QPen(HUD_GREEN_DIM, 1.0))
        for i in range(-4, 5):
            ty = cy + i * (tape_h / 8.0)
            is_mid = (i == 0)
            tick_w = 8 if is_mid else 4
            p.drawLine(QPointF(ladder_x, ty), QPointF(ladder_x - tick_w, ty))

        # Chevron Pointer Box
        p.setPen(QPen(HUD_GREEN, 1.8))
        chevron = QPainterPath()
        chevron.moveTo(ladder_x, cy)
        chevron.lineTo(ladder_x - 12, cy - 9)
        chevron.lineTo(ladder_x - 56, cy - 9)
        chevron.lineTo(ladder_x - 56, cy + 9)
        chevron.lineTo(ladder_x - 12, cy + 9)
        chevron.closeSubpath()
        p.setBrush(QBrush(QColor(0x06, 0x1a, 0x10, 0xd0)))
        p.drawPath(chevron)

        p.setFont(QFont("Bahnschrift", 12, QFont.Weight.Bold))
        spd_str = f"{int(self._speed)}"
        p.drawText(QPointF(ladder_x - 50, cy + 4), spd_str)

        p.setFont(QFont("Bahnschrift", 9, QFont.Weight.DemiBold))
        p.drawText(QPointF(ladder_x - 52, cy - tape_h / 2 - 6), "SPEED")
        p.setFont(QFont("Bahnschrift", 8))
        p.setPen(QPen(HUD_GREEN_DIM, 1))
        p.drawText(QPointF(ladder_x - 52, cy + tape_h / 2 + 14), "cm/s")

    def _draw_altitude_ladder(self, p: QPainter, cx: float, cy: float, H: float):
        ladder_x = cx + 195.0
        tape_h   = 170.0

        p.setPen(QPen(HUD_GREEN, 1.6))
        p.drawLine(QPointF(ladder_x, cy - tape_h / 2), QPointF(ladder_x, cy + tape_h / 2))
        p.drawLine(QPointF(ladder_x, cy - tape_h / 2), QPointF(ladder_x - 8, cy - tape_h / 2))
        p.drawLine(QPointF(ladder_x, cy + tape_h / 2), QPointF(ladder_x - 8, cy + tape_h / 2))

        p.setPen(QPen(HUD_GREEN_DIM, 1.0))
        for i in range(-4, 5):
            ty = cy + i * (tape_h / 8.0)
            is_mid = (i == 0)
            tick_w = 8 if is_mid else 4
            p.drawLine(QPointF(ladder_x, ty), QPointF(ladder_x + tick_w, ty))

        p.setPen(QPen(HUD_GREEN, 1.8))
        chevron = QPainterPath()
        chevron.moveTo(ladder_x, cy)
        chevron.lineTo(ladder_x + 12, cy - 9)
        chevron.lineTo(ladder_x + 64, cy - 9)
        chevron.lineTo(ladder_x + 64, cy + 9)
        chevron.lineTo(ladder_x + 12, cy + 9)
        chevron.closeSubpath()
        p.setBrush(QBrush(QColor(0x06, 0x1a, 0x10, 0xd0)))
        p.drawPath(chevron)

        p.setFont(QFont("Bahnschrift", 12, QFont.Weight.Bold))
        alt_str = f"{int(self._alt)}"
        p.drawText(QPointF(ladder_x + 16, cy + 4), alt_str)

        p.setFont(QFont("Bahnschrift", 9, QFont.Weight.DemiBold))
        p.drawText(QPointF(ladder_x + 16, cy - tape_h / 2 - 6), "ALT")
        p.setFont(QFont("Bahnschrift", 8))
        p.setPen(QPen(HUD_GREEN_DIM, 1))
        p.drawText(QPointF(ladder_x + 16, cy + tape_h / 2 + 14), "cm")

    def _draw_heading_tape(self, p: QPainter, cx: float, W: float):
        tape_y = 40.0
        tape_w = 320.0

        p.setPen(QPen(HUD_GREEN, 1.5))
        caret = QPainterPath()
        caret.moveTo(cx, tape_y + 12)
        caret.lineTo(cx - 5, tape_y + 4)
        caret.lineTo(cx + 5, tape_y + 4)
        caret.closeSubpath()
        p.setBrush(QBrush(HUD_GREEN))
        p.drawPath(caret)

        p.setPen(QPen(HUD_GREEN_DIM, 1.0))
        p.drawLine(QPointF(cx - tape_w / 2, tape_y), QPointF(cx + tape_w / 2, tape_y))

        px_per_deg = tape_w / 60.0
        cardinals = {0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW"}

        for deg in range(0, 360, 5):
            diff = (deg - self._yaw + 180) % 360 - 180
            if abs(diff) > 35:
                continue

            x = cx + diff * px_per_deg
            is_cardinal = deg in cardinals
            is_major    = deg % 15 == 0

            tick_len = 8.0 if is_cardinal else (5.0 if is_major else 3.0)
            p.setPen(QPen(HUD_GREEN if is_cardinal else HUD_GREEN_DIM, 1.2 if is_cardinal else 1.0))
            p.drawLine(QPointF(x, tape_y), QPointF(x, tape_y - tick_len))

            if is_cardinal:
                p.setFont(QFont("Bahnschrift", 10, QFont.Weight.Bold))
                lbl = cardinals[deg]
                tw = p.fontMetrics().horizontalAdvance(lbl)
                p.drawText(QPointF(x - tw / 2, tape_y - tick_len - 3), lbl)
            elif is_major:
                p.setFont(QFont("Bahnschrift", 8))
                lbl = f"{deg // 10:02d}"
                tw = p.fontMetrics().horizontalAdvance(lbl)
                p.drawText(QPointF(x - tw / 2, tape_y - tick_len - 3), lbl)

    def _draw_radio_banner(self, p: QPainter, cx: float):
        banner_y = 70.0
        p.setFont(QFont("Bahnschrift", 10, QFont.Weight.DemiBold))
        p.setPen(QPen(HUD_GREEN, 1.0))

        text = f"« TACTICAL COMMS: {self._msg} »"
        tw = p.fontMetrics().horizontalAdvance(text)
        p.drawText(QPointF(cx - tw / 2, banner_y), text)
