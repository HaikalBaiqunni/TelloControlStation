"""
src/ui/widgets/fighter_hud.py
Fighter-jet HUD overlay widget (pitch ladder, bank scale, scrolling speed/altitude tapes,
heading tape, mission line and master-caution banner).

Typography: Bahnschrift (DIN 1451 aerospace standard). Palette comes from src/ui/theme.py.
"""

import math
import time
from typing import Optional

from PySide6.QtCore import Qt, QPointF, QRectF, QTimer
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import QWidget

from src.ui import theme

HUD_GREEN     = theme.ACCENT                      # primary vector colour
HUD_GREEN_GLO = theme.rgba(theme.ACCENT, 0x44)    # glow / transparency
HUD_GREEN_DIM = theme.rgba(theme.ACCENT, 0x99)    # minor ticks
HUD_ALERT     = theme.ALERT
HUD_AMBER     = theme.WARN
PANEL_BG      = QColor(0x06, 0x12, 0x1a, 0xd0)

SPD_PX = 1.2     # pixels per cm/s on the speed tape
ALT_PX = 1.4     # pixels per cm on the altitude tape


class FighterHUDWidget(QWidget):
    """Transparent vector HUD drawn directly over the camera feed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._roll: float  = 0.0
        self._pitch: float = 0.0
        self._yaw: float   = 0.0
        self._alt: float   = 0.0
        self._speed: float = 0.0
        self._tof: float   = 0.0
        self._bat: Optional[int] = None
        self._msg: str     = "ALL SENSORS NOMINAL"
        self._mission: str = ""
        self._caution: str = ""
        self._blink = QTimer(self)
        self._blink.setInterval(250)
        self._blink.timeout.connect(self.update)

    # ── API ──────────────────────────────────────────────────────────────

    def update_telemetry(self, roll: float, pitch: float, yaw: float, alt: float, speed: float,
                         tof: float = 0.0, bat: Optional[int] = None):
        self._roll  = roll
        self._pitch = pitch
        self._yaw   = yaw % 360
        self._alt   = alt
        self._speed = speed
        self._tof   = tof
        self._bat   = bat
        self.update()

    def set_radio_message(self, msg: str):
        self._msg = msg
        self.update()

    def set_mission_info(self, text: str):
        """Bottom line, e.g. 'WP 2/5  DIST 4.2 M  ETA 00:08'. Empty string hides it."""
        if text != self._mission:
            self._mission = text
            self.update()

    def set_caution(self, text: str):
        """Flashing master-caution banner. Empty string clears it."""
        if text != self._caution:
            self._caution = text
            if text:
                self._blink.start()
            else:
                self._blink.stop()
            self.update()

    # ── Paint ────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        W = float(self.width())
        H = float(self.height())
        cx, cy = W / 2.0, H / 2.0

        self._draw_bank_scale(p, cx, cy, H)
        self._draw_pitch_ladder(p, cx, cy, H)
        self._draw_aircraft_watermark(p, cx, cy)
        self._draw_speed_tape(p, cx, cy, W, H)
        self._draw_altitude_tape(p, cx, cy, W, H)
        self._draw_heading_tape(p, cx, W)
        self._draw_radio_banner(p, cx)
        self._draw_footer(p, cx, W, H)

    def _draw_aircraft_watermark(self, p: QPainter, cx: float, cy: float):
        p.setPen(QPen(HUD_GREEN, 2.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        r = 9.0
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.drawLine(QPointF(cx - 5, cy - 2), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx, cy + 4),     QPointF(cx + 5, cy - 2))
        p.drawLine(QPointF(cx - 28, cy), QPointF(cx - r, cy))
        p.drawLine(QPointF(cx + r, cy),  QPointF(cx + 28, cy))

    def _draw_bank_scale(self, p: QPainter, cx: float, cy: float, H: float):
        r = min(H * 0.40, 215.0)
        p.save()
        p.translate(cx, cy)
        p.setPen(QPen(HUD_GREEN_DIM, 1.2))
        for a in (-45, -30, -20, -10, 0, 10, 20, 30, 45):
            major = a % 30 == 0
            p.save()
            p.rotate(a)
            p.drawLine(QPointF(0, -r), QPointF(0, -r - (10 if major else 6)))
            p.restore()
        p.rotate(-self._roll)
        tri = QPainterPath()
        tri.moveTo(0, -r + 3)
        tri.lineTo(-6, -r + 15)
        tri.lineTo(6, -r + 15)
        tri.closeSubpath()
        p.setBrush(QBrush(HUD_GREEN))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(tri)
        p.restore()

    def _draw_pitch_ladder(self, p: QPainter, cx: float, cy: float, H: float):
        p.save()
        p.translate(cx, cy)
        p.rotate(-self._roll)

        px_per_deg = H / 48.0
        pitch_shift = self._pitch * px_per_deg
        bar_width, gap_width = 80.0, 34.0

        for deg in range(-30, 35, 5):
            if deg == 0:
                continue
            y = -pitch_shift - (deg * px_per_deg)
            if abs(y) > H * 0.34:
                continue

            is_positive = deg > 0
            is_major = deg % 10 == 0
            bw = bar_width if is_major else bar_width * 0.72
            tick = 6.0

            if is_positive:
                p.setPen(QPen(HUD_GREEN, 1.6))
                p.drawLine(QPointF(-bw, y), QPointF(-gap_width, y))
                p.drawLine(QPointF(-bw, y), QPointF(-bw, y + tick))
                p.drawLine(QPointF(gap_width, y), QPointF(bw, y))
                p.drawLine(QPointF(bw, y), QPointF(bw, y + tick))
            else:
                p.setPen(QPen(HUD_GREEN, 1.4, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(-bw, y), QPointF(-gap_width, y))
                p.drawLine(QPointF(-bw, y), QPointF(-bw, y - tick))
                p.drawLine(QPointF(gap_width, y), QPointF(bw, y))
                p.drawLine(QPointF(bw, y), QPointF(bw, y - tick))

            if is_major:
                p.setPen(QPen(HUD_GREEN, 1))
                p.setFont(QFont(theme.FONT_UI, 9, QFont.Weight.DemiBold))
                p.drawText(QPointF(-bw - 20, y + 4), str(abs(deg)))
                p.drawText(QPointF(bw + 6, y + 4), str(abs(deg)))

        y0 = -pitch_shift
        p.setPen(QPen(HUD_GREEN_DIM, 1.0, Qt.PenStyle.DashDotLine))
        p.drawLine(QPointF(-bar_width * 1.5, y0), QPointF(-gap_width, y0))
        p.drawLine(QPointF(gap_width, y0), QPointF(bar_width * 1.5, y0))
        p.restore()

    # Scrolling tapes ------------------------------------------------------

    def _tape(self, p: QPainter, x: float, cy: float, tape_h: float, value: float, px: float,
              step: int, label_every: int, side: int, title: str, unit: str, box_w: float):
        """Vertical tape. side=-1: ticks/readout on the left of x; side=+1: right."""
        half = tape_h / 2.0
        p.setPen(QPen(HUD_GREEN, 1.6))
        p.drawLine(QPointF(x, cy - half), QPointF(x, cy + half))

        p.save()
        p.setClipRect(QRectF(x - 80, cy - half, 160, tape_h))
        lo = int((value - half / px) // step) * step
        hi = int((value + half / px) // step + 2) * step
        p.setFont(QFont(theme.FONT_MONO, 8))
        for v in range(lo, hi + 1, step):
            if v < 0:
                continue
            y = cy - (v - value) * px
            major = v % label_every == 0
            L = 9 if major else 4
            p.setPen(QPen(HUD_GREEN if major else HUD_GREEN_DIM, 1.2 if major else 1.0))
            p.drawLine(QPointF(x, y), QPointF(x - side * L, y))
            if major and abs(y - cy) > 14:
                p.setPen(QPen(HUD_GREEN, 1))
                if side < 0:
                    p.drawText(QRectF(x + 4, y - 7, 40, 14), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(v))
                else:
                    p.drawText(QRectF(x - 44, y - 7, 40, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(v))
        p.restore()

        # readout chevron
        s = side
        chevron = QPainterPath()
        chevron.moveTo(x, cy)
        chevron.lineTo(x + s * 12, cy - 10)
        chevron.lineTo(x + s * (12 + box_w), cy - 10)
        chevron.lineTo(x + s * (12 + box_w), cy + 10)
        chevron.lineTo(x + s * 12, cy + 10)
        chevron.closeSubpath()
        p.setPen(QPen(HUD_GREEN, 1.8))
        p.setBrush(QBrush(PANEL_BG))
        p.drawPath(chevron)
        p.setFont(QFont(theme.FONT_MONO, 12, QFont.Weight.Bold))
        rect = QRectF(min(x + s * 12, x + s * (12 + box_w)), cy - 10, box_w, 20)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{int(value)}")

        # title + unit
        p.setFont(QFont(theme.FONT_UI, 9, QFont.Weight.DemiBold))
        p.drawText(QRectF(min(x + s * 12, x + s * 52), cy - half - 20, 60, 14),
                   Qt.AlignmentFlag.AlignLeft if s > 0 else Qt.AlignmentFlag.AlignRight, title)
        p.setFont(QFont(theme.FONT_UI, 8))
        p.setPen(QPen(HUD_GREEN_DIM, 1))
        p.drawText(QRectF(min(x + s * 12, x + s * 52), cy + half + 4, 60, 14),
                   Qt.AlignmentFlag.AlignLeft if s > 0 else Qt.AlignmentFlag.AlignRight, unit)

    def _draw_speed_tape(self, p: QPainter, cx: float, cy: float, W: float, H: float):
        off = min(W * 0.36, 215.0)
        self._tape(p, cx - off, cy, min(H * 0.42, 230.0), self._speed, SPD_PX, 10, 50, -1, "SPEED", "cm/s", 46)

    def _draw_altitude_tape(self, p: QPainter, cx: float, cy: float, W: float, H: float):
        off = min(W * 0.36, 215.0)
        self._tape(p, cx + off, cy, min(H * 0.42, 230.0), self._alt, ALT_PX, 10, 50, +1, "ALT", "cm", 54)

    def _draw_heading_tape(self, p: QPainter, cx: float, W: float):
        tape_y, tape_w = 40.0, min(320.0, W - 40.0)

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
            if abs(diff) > 30:
                continue
            x = cx + diff * px_per_deg
            is_cardinal = deg in cardinals
            is_major = deg % 15 == 0
            tick = 8.0 if is_cardinal else (5.0 if is_major else 3.0)
            p.setPen(QPen(HUD_GREEN if is_cardinal else HUD_GREEN_DIM, 1.2 if is_cardinal else 1.0))
            p.drawLine(QPointF(x, tape_y), QPointF(x, tape_y - tick))
            if is_cardinal:
                p.setFont(QFont(theme.FONT_UI, 10, QFont.Weight.Bold))
                lbl = cardinals[deg]
                tw = p.fontMetrics().horizontalAdvance(lbl)
                p.drawText(QPointF(x - tw / 2, tape_y - tick - 3), lbl)
            elif is_major:
                p.setFont(QFont(theme.FONT_UI, 8))
                lbl = f"{deg // 10:02d}"
                tw = p.fontMetrics().horizontalAdvance(lbl)
                p.drawText(QPointF(x - tw / 2, tape_y - tick - 3), lbl)

        p.setFont(QFont(theme.FONT_MONO, 11, QFont.Weight.Bold))
        p.setPen(QPen(HUD_GREEN))
        p.drawText(QRectF(cx - 30, tape_y + 14, 60, 18), Qt.AlignmentFlag.AlignCenter, f"{int(self._yaw):03d}°")

    def _draw_radio_banner(self, p: QPainter, cx: float):
        p.setFont(QFont(theme.FONT_UI, 9, QFont.Weight.DemiBold))
        p.setPen(QPen(HUD_GREEN_DIM, 1.0))
        text = f"« {self._msg} »"
        tw = p.fontMetrics().horizontalAdvance(text)
        p.drawText(QPointF(cx - tw / 2, 88.0), text)

    def _draw_footer(self, p: QPainter, cx: float, W: float, H: float):
        y = H - 14.0
        p.setFont(QFont(theme.FONT_MONO, 10, QFont.Weight.DemiBold))
        p.setPen(QPen(HUD_GREEN))
        if self._mission:
            tw = p.fontMetrics().horizontalAdvance(self._mission)
            p.drawText(QPointF(cx - tw / 2, y), self._mission)

        p.setFont(QFont(theme.FONT_MONO, 9))
        p.setPen(QPen(HUD_GREEN_DIM))
        if self._bat is not None:
            p.drawText(QPointF(12, y), f"BAT {self._bat}%   TOF {int(self._tof)}CM")

        if self._caution and int(time.time() * 2) % 2 == 0:
            p.setFont(QFont(theme.FONT_UI, 11, QFont.Weight.Bold))
            p.setPen(QPen(HUD_AMBER))
            msg = f"⚠ MASTER CAUTION · {self._caution}"
            tw = p.fontMetrics().horizontalAdvance(msg)
            p.drawText(QPointF(cx - tw / 2, y - 22), msg)
