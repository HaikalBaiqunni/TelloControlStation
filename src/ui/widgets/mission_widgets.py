"""
src/ui/widgets/mission_widgets.py
Mission progress strip, upcoming-waypoint status list and altitude profile.
"""

import math
import time

from PySide6.QtCore import Qt, QPointF, QRectF, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from src.drone.mission import Waypoint, cumulative, estimate, seg_length
from src.ui import theme
from src.ui.mission_model import MissionModel


def mmss(sec: float) -> str:
    sec = max(0, int(round(sec)))
    return f"{sec // 60:02d}:{sec % 60:02d}"


class _Ticking(QWidget):
    """Repaints while visible so pulses and live values stay smooth."""

    def __init__(self, model: MissionModel, pose, parent=None):
        super().__init__(parent)
        self.m, self.pose = model, pose
        self._t0 = time.time()
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self.update)
        model.changed.connect(self.update)
        model.progress_changed.connect(self.update)

    def showEvent(self, e):
        super().showEvent(e)
        self._timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()

    def remaining(self):
        """(length_cm, time_s) still to fly; the whole plan when idle."""
        items = self.m.items
        if self.m.state == MissionModel.RUNNING:
            t = max(1, min(self.m.target, len(items) - 1))
            here = Waypoint("GO", self.pose.x, self.pose.y, self.pose.alt)
            length, secs, _ = estimate([here] + items[t:])
            return length, secs
        if self.m.state == MissionModel.DONE:
            return 0.0, 0.0
        length, secs, _ = estimate(items)
        return length, secs


class MissionStrip(_Ticking):
    """Timeline H → LAND with a marker for the drone position."""

    def __init__(self, model, pose, parent=None):
        super().__init__(model, pose, parent)
        self.setMinimumHeight(70)

    def _u(self) -> float:
        items, st = self.m.items, self.m.state
        n = len(items) - 1
        if n <= 0 or st == MissionModel.IDLE:
            return 0.0
        if st == MissionModel.DONE:
            return 1.0
        t = max(1, min(self.m.target, n))
        a, b = items[t - 1], items[t]
        seg = seg_length(a, b)
        frac = 1.0 if seg < 1 else min(1.0, math.hypot(self.pose.x - a.x, self.pose.y - a.y) / seg)
        return (t - 1 + frac) / n

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        items, st = self.m.items, self.m.state
        n = max(1, len(items) - 1)
        u = self._u()
        t = time.time() - self._t0
        x0, x1 = 28.0, W - 28.0
        y = H * 0.56
        X = lambda f: x0 + f * (x1 - x0)

        p.setPen(QPen(QColor(255, 255, 255, 34), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(x0, y), QPointF(x1, y))
        p.setPen(QPen(theme.OK, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(x0, y), QPointF(X(u), y))

        spacing = (x1 - x0) / n
        p.setFont(QFont(theme.FONT_MONO, 7))
        for i, w in enumerate(items):
            f = i / n
            done = st == MissionModel.DONE or (st == MissionModel.RUNNING and i < self.m.target)
            active = st == MissionModel.RUNNING and i == self.m.target
            if active:
                ph = (t * 1.5) % 1.0
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(255, 255, 255, int(255 * (1 - ph))), 2))
                p.drawEllipse(QPointF(X(f), y), 7 + ph * 9, 7 + ph * 9)
            p.setBrush(QBrush(theme.OK if done else QColor(255, 255, 255) if active else QColor(11, 22, 32)))
            p.setPen(QPen(theme.OK if done else QColor(255, 255, 255) if active else theme.ACCENT, 2))
            p.drawEllipse(QPointF(X(f), y), 7, 7)
            p.setPen(QPen(theme.TEXT if (done or active) else theme.MUTED))
            label = f"{'H' if i == 0 else i} {w.cmd}" if spacing >= 62 else ("H" if i == 0 else str(i))
            p.drawText(QRectF(X(f) - 40, y + 11, 80, 14), Qt.AlignmentFlag.AlignCenter, label)

        if st != MissionModel.IDLE:
            p.setBrush(QBrush(theme.ACCENT))
            p.setPen(Qt.PenStyle.NoPen)
            tri = QPainterPath()
            tri.moveTo(X(u), y - 9)
            tri.lineTo(X(u) - 6, y - 21)
            tri.lineTo(X(u) + 6, y - 21)
            tri.closeSubpath()
            p.drawPath(tri)

        length, secs = self.remaining()
        p.setFont(QFont(theme.FONT_UI, 8, QFont.Weight.DemiBold))
        p.setPen(QPen(theme.MUTED))
        head = (f"MISSION PROGRESS  {u * 100:.0f}%" if st != MissionModel.IDLE
                else "MISSION READY" if len(items) > 2 else "NO MISSION - ADD WAYPOINTS IN FLIGHT PLAN")
        p.drawText(QRectF(28, 4, W / 2, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, head)
        tag = "REMAINING" if st == MissionModel.RUNNING else "PLANNED"
        p.drawText(QRectF(W / 2, 4, W / 2 - 28, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   f"{tag} {length / 100:.1f} m · ETA {mmss(secs)}")


class MissionStatusList(_Ticking):
    """Three rows around the active waypoint: ✓ done / ▶ active / ○ pending."""

    ROW_H = 26

    def __init__(self, model, pose, parent=None):
        super().__init__(model, pose, parent)
        self.setFixedHeight(self.ROW_H * 3 + 6)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        items, st = self.m.items, self.m.state
        n = len(items)
        cur = self.m.target if st == MissionModel.RUNNING else (n if st == MissionModel.DONE else 1)
        first = max(1, min(cur - 1, n - 3))
        W = self.width()
        for k in range(3):
            i = first + k
            if i >= n:
                break
            w = items[i]
            done = st == MissionModel.DONE or (st == MissionModel.RUNNING and i < cur)
            active = st == MissionModel.RUNNING and i == cur
            top = 3 + k * self.ROW_H
            if active:
                p.fillRect(QRectF(0, top, W, self.ROW_H - 2), theme.rgba(theme.ACCENT, 28))
            c = QPointF(16, top + self.ROW_H / 2 - 1)
            p.setBrush(QBrush(theme.OK if done else QColor(255, 255, 255) if active else QColor(11, 22, 32)))
            p.setPen(QPen(theme.OK if done else QColor(255, 255, 255) if active else theme.ACCENT, 1.6))
            p.drawEllipse(c, 9, 9)
            p.setPen(QPen(QColor(0, 0, 0) if (done or active) else theme.ACCENT))
            p.setFont(QFont(theme.FONT_UI, 8, QFont.Weight.Bold))
            p.drawText(QRectF(c.x() - 9, c.y() - 9, 18, 18), Qt.AlignmentFlag.AlignCenter,
                       "✓" if done else "▶" if active else "○")
            p.setFont(QFont(theme.FONT_MONO, 9))
            p.setPen(QPen(theme.rgba(theme.TEXT, 130 if done else 255)))
            desc = f"{i}  {w.cmd}" + (f" → ({w.x / 100:.1f}, {w.y / 100:.1f})" if w.cmd == "GO"
                                      else f" {w.param}" if w.param else "")
            p.drawText(QRectF(32, top, W - 90, self.ROW_H - 2), Qt.AlignmentFlag.AlignVCenter, desc)
            p.setPen(QPen(theme.MUTED))
            p.drawText(QRectF(W - 60, top, 56, self.ROW_H - 2),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, f"{w.alt / 100:.1f} m")


class AltitudeProfile(_Ticking):
    """Altitude vs. path distance along the planned mission."""

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        items = self.m.items
        cum, total = cumulative(items)
        top = max(300.0, max(w.alt for w in items) * 1.15)
        L, R, T, B = 34.0, 12.0, 8.0, 20.0
        X = lambda d: L + (d / total if total > 0 else 0) * (W - L - R)
        Y = lambda a: H - B - a / top * (H - T - B)

        p.setFont(QFont(theme.FONT_MONO, 7))
        step = 100.0 if top <= 500 else 200.0
        a = 0.0
        while a <= top:
            p.setPen(QPen(QColor(255, 255, 255, 22), 1))
            p.drawLine(QPointF(L, Y(a)), QPointF(W - R, Y(a)))
            p.setPen(QPen(theme.MUTED))
            p.drawText(QPointF(2, Y(a) + 3), f"{a / 100:g}m")
            a += step

        pts = [QPointF(X(cum[i]), Y(w.alt)) for i, w in enumerate(items)]
        if len(pts) > 1:
            area = QPainterPath(QPointF(pts[0].x(), Y(0)))
            for q in pts:
                area.lineTo(q)
            area.lineTo(QPointF(pts[-1].x(), Y(0)))
            area.closeSubpath()
            p.fillPath(area, QBrush(theme.rgba(theme.ACCENT, 34)))
            line = QPainterPath(pts[0])
            for q in pts[1:]:
                line.lineTo(q)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(theme.ACCENT, 2))
            p.drawPath(line)

        for i, q in enumerate(pts):
            sel = i == self.m.selected
            p.setBrush(QBrush(QColor(255, 255, 255) if sel else theme.ACCENT))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(q, 4.5 if sel else 3.5, 4.5 if sel else 3.5)
            p.setPen(QPen(theme.MUTED))
            p.drawText(QRectF(q.x() - 12, H - B + 3, 24, 12), Qt.AlignmentFlag.AlignCenter, "H" if i == 0 else str(i))
