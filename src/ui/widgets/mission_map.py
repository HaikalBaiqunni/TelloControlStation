"""
src/ui/widgets/mission_map.py
Mission map: local metric grid (no GPS) with waypoints, planned path, live drone, trail,
geofence and mission progress.

  editable=True  -> planner: click = add waypoint, drag = move, right-click = delete,
                    wheel = zoom, middle-drag = pan.
  live=True      -> shows the drone, trail and progress (done / active / pending).
"""

import math
import time
from typing import List, Optional

from PySide6.QtCore import Qt, QPointF, QRectF, QTimer
from PySide6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen, QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from src.drone.mission import seg_length
from src.ui import theme
from src.ui.mission_model import MissionModel

MARKER_R = 11.0


class MissionMapWidget(QWidget):
    def __init__(self, model: MissionModel, pose, editable: bool = False, live: bool = True,
                 labels: bool = True, show_progress: bool = True, auto_fit: bool = False, parent=None):
        super().__init__(parent)
        self.m = model
        self.pose = pose
        self.editable = editable
        self.live = live
        self.labels = labels
        self.show_progress = show_progress
        self._auto = auto_fit
        self._cx, self._cy = 300.0, 100.0      # world centre (cm)
        self._ppc = 0.2                         # pixels per cm
        self._drag = -1
        self._hover = -1
        self._pan_from: Optional[QPointF] = None
        self._mouse_world = None
        self._fitted = False
        self._t0 = time.time()

        self.setMouseTracking(True)
        self.setMinimumSize(220, 160)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        if editable:
            self.setCursor(Qt.CursorShape.CrossCursor)

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

        self.m.changed.connect(self.update)
        self.m.progress_changed.connect(self.update)
        self.m.selection_changed.connect(lambda *_: self.update())

    # ── View ─────────────────────────────────────────────────────────────

    def showEvent(self, e):
        super().showEvent(e)
        self._timer.start()
        if not self._fitted:
            self.fit()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()

    def set_auto_fit(self, on: bool):
        self._auto = on
        if on:
            self.fit(smooth=False)

    def fit(self, smooth: bool = False):
        pts = [(w.x, w.y) for w in self.m.items] + [(0.0, 0.0), (self.pose.x, self.pose.y)]
        minx, maxx = min(p[0] for p in pts), max(p[0] for p in pts)
        miny, maxy = min(p[1] for p in pts), max(p[1] for p in pts)
        w, h = max(maxx - minx, 600.0), max(maxy - miny, 600.0)
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        ppc = max(0.02, min((self.width() - 90) / w, (self.height() - 90) / h))
        if smooth:
            k = 0.12
            self._cx += (cx - self._cx) * k
            self._cy += (cy - self._cy) * k
            self._ppc += (ppc - self._ppc) * k
        else:
            self._cx, self._cy, self._ppc = cx, cy, ppc
        self._fitted = self.width() > 50
        self.update()

    def _tick(self):
        if self._auto:
            self.fit(smooth=True)
        else:
            self.update()

    def _w2s(self, x: float, y: float) -> QPointF:
        return QPointF(self.width() / 2 + (x - self._cx) * self._ppc,
                       self.height() / 2 - (y - self._cy) * self._ppc)

    def _s2w(self, px: float, py: float):
        return ((px - self.width() / 2) / self._ppc + self._cx,
                -(py - self.height() / 2) / self._ppc + self._cy)

    def _marker_pts(self) -> List[QPointF]:
        """Screen positions of the markers; stacked items at the same spot are fanned out."""
        pts: List[QPointF] = []
        for w in self.m.items:
            p = self._w2s(w.x, w.y)
            n = sum(1 for q in pts if math.hypot(q.x() - p.x(), q.y() - p.y()) < MARKER_R * 1.4)
            pts.append(QPointF(p.x() + 17 * n, p.y() - 17 * n))
        return pts

    def _hit(self, px: float, py: float) -> int:
        best, best_d = -1, MARKER_R + 4
        for i, q in enumerate(self._marker_pts()):
            d = math.hypot(q.x() - px, q.y() - py)
            if d < best_d:
                best, best_d = i, d
        return best

    # ── Mouse ────────────────────────────────────────────────────────────

    def mousePressEvent(self, e: QMouseEvent):
        pos = e.position()
        if e.button() == Qt.MouseButton.MiddleButton:
            self._pan_from = pos
            self._auto = False
            return
        if not self.editable:
            return
        i = self._hit(pos.x(), pos.y())
        if e.button() == Qt.MouseButton.RightButton:
            if i > 0:
                self.m.remove(i)
            return
        if e.button() == Qt.MouseButton.LeftButton:
            if i >= 0:
                self.m.select(i)
                self._drag = i
            else:
                x, y = self._s2w(pos.x(), pos.y())
                self.m.add_go(round(x / 5) * 5, round(y / 5) * 5)

    def mouseMoveEvent(self, e: QMouseEvent):
        pos = e.position()
        self._mouse_world = self._s2w(pos.x(), pos.y())
        if self._pan_from is not None:
            d = pos - self._pan_from
            self._cx -= d.x() / self._ppc
            self._cy += d.y() / self._ppc
            self._pan_from = pos
        elif self._drag > 0:
            x, y = self._s2w(pos.x(), pos.y())
            self.m.move(self._drag, round(x / 5) * 5, round(y / 5) * 5)
        else:
            self._hover = self._hit(pos.x(), pos.y()) if self.editable else -1
        self.update()

    def mouseReleaseEvent(self, e: QMouseEvent):
        self._drag = -1
        self._pan_from = None

    def mouseDoubleClickEvent(self, e: QMouseEvent):
        if self.editable:
            self.mousePressEvent(e)      # fast second click still adds / selects
        else:
            self.set_auto_fit(True)

    def leaveEvent(self, e):
        self._mouse_world = None
        self._hover = -1
        self.update()

    def wheelEvent(self, e: QWheelEvent):
        if not (self.editable or self.live):
            return
        self._auto = False
        pos = e.position()
        wx, wy = self._s2w(pos.x(), pos.y())
        k = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self._ppc = max(0.03, min(3.0, self._ppc * k))
        # keep the point under the cursor fixed
        nx, ny = self._s2w(pos.x(), pos.y())
        self._cx += wx - nx
        self._cy += wy - ny
        self.update()

    # ── Paint ────────────────────────────────────────────────────────────

    def _wp_state(self, i: int) -> str:
        if not self.show_progress:
            return "normal"
        st = self.m.state
        if st == MissionModel.DONE:
            return "done"
        if st == MissionModel.RUNNING:
            return "done" if i < self.m.target else ("active" if i == self.m.target else "pending")
        return "pending"

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        t = time.time() - self._t0

        p.fillRect(self.rect(), theme.MAP_BG)
        self._draw_grid(p, W, H)
        self._draw_fence(p)
        self._draw_path(p)
        self._draw_markers(p, t)
        if self.live:
            self._draw_drone(p)
        self._draw_overlay(p, W, H)

    def _draw_grid(self, p: QPainter, W: int, H: int):
        step_px = self._ppc * 100
        x0, y0 = self._s2w(0, H)
        x1, y1 = self._s2w(W, 0)
        p.setFont(QFont(theme.FONT_MONO, 7))
        for k in range(math.floor(x0 / 100) - 1, math.ceil(x1 / 100) + 2):
            major = k % 5 == 0
            if not major and step_px < 9:
                continue
            sx = self._w2s(k * 100, 0).x()
            p.setPen(QPen(theme.rgba(theme.ACCENT, 46 if major else 16), 1))
            p.drawLine(QPointF(sx, 0), QPointF(sx, H))
            if major:
                p.setPen(QPen(theme.rgba(theme.TEXT, 110)))
                p.drawText(QPointF(sx + 3, H - 5), f"{k} m")
        for k in range(math.floor(y0 / 100) - 1, math.ceil(y1 / 100) + 2):
            major = k % 5 == 0
            if not major and step_px < 9:
                continue
            sy = self._w2s(0, k * 100).y()
            p.setPen(QPen(theme.rgba(theme.ACCENT, 46 if major else 16), 1))
            p.drawLine(QPointF(0, sy), QPointF(W, sy))
            if major:
                p.setPen(QPen(theme.rgba(theme.TEXT, 110)))
                p.drawText(QPointF(4, sy - 3), f"{k} m")

    def _draw_fence(self, p: QPainter):
        o = self._w2s(0, 0)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(theme.rgba(theme.ACCENT, 50), 1, Qt.PenStyle.DashLine))
        for r in (500, 1000):
            p.drawEllipse(o, r * self._ppc, r * self._ppc)
        fr = self.m.geofence_cm * self._ppc
        p.setPen(QPen(theme.rgba(theme.ALERT, 160), 1.3, Qt.PenStyle.DashLine))
        p.drawEllipse(o, fr, fr)
        p.setFont(QFont(theme.FONT_MONO, 7))
        p.setPen(QPen(theme.ALERT))
        p.drawText(QPointF(o.x() + 8, o.y() - fr + 12), f"GEOFENCE {self.m.geofence_cm / 100:.0f} m")

    def _draw_path(self, p: QPainter):
        items = self.m.items
        if len(items) < 2:
            return
        pts = [self._w2s(w.x, w.y) for w in items]
        prog = self.show_progress and self.m.state != MissionModel.IDLE

        path = QPainterPath(pts[0])
        for q in pts[1:]:
            path.lineTo(q)
        pen = QPen(theme.rgba(theme.ACCENT, 255 if not self.show_progress else 140), 2.2)
        if self.show_progress:
            pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        if prog:
            upto = len(items) if self.m.state == MissionModel.DONE else max(0, min(self.m.target, len(items)))
            done = QPainterPath(pts[0])
            for q in pts[1:upto]:
                done.lineTo(q)
            if self.m.state == MissionModel.RUNNING:
                done.lineTo(self._w2s(self.pose.x, self.pose.y))
            p.setPen(QPen(theme.OK, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(done)
            if self.m.state == MissionModel.RUNNING and 0 <= self.m.target < len(items):
                a = self._w2s(self.pose.x, self.pose.y)
                b = pts[self.m.target]
                p.setPen(QPen(QColor(255, 255, 255, 200), 1, Qt.PenStyle.DotLine))
                p.drawLine(a, b)
                d = math.hypot(items[self.m.target].x - self.pose.x, items[self.m.target].y - self.pose.y)
                p.setFont(QFont(theme.FONT_MONO, 8, QFont.Weight.Bold))
                p.setPen(QPen(QColor(255, 255, 255)))
                p.drawText(QPointF((a.x() + b.x()) / 2 + 6, (a.y() + b.y()) / 2 - 6), f"{d / 100:.1f} m")

        # direction arrows + segment length
        p.setFont(QFont(theme.FONT_MONO, 7))
        for i in range(1, len(items)):
            a, b = pts[i - 1], pts[i]
            if math.hypot(b.x() - a.x(), b.y() - a.y()) < 34:
                continue
            mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
            ang = math.degrees(math.atan2(b.y() - a.y(), b.x() - a.x()))
            p.save()
            p.translate(mid)
            p.rotate(ang)
            tri = QPainterPath()
            tri.moveTo(7, 0)
            tri.lineTo(-5, -5)
            tri.lineTo(-5, 5)
            tri.closeSubpath()
            p.setBrush(QBrush(theme.ACCENT))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPath(tri)
            p.restore()
            p.setPen(QPen(theme.rgba(theme.TEXT, 170)))
            p.drawText(QPointF(mid.x() + 8, mid.y() - 8), f"{seg_length(items[i - 1], items[i]) / 100:.1f} m")

    def _draw_markers(self, p: QPainter, t: float):
        items = self.m.items
        fence = self.m.geofence_cm
        for i, (w, q) in enumerate(zip(items, self._marker_pts())):
            st = self._wp_state(i)
            sel = (i == self.m.selected) and not self.show_progress
            if sel or i == self._hover:
                p.setBrush(QBrush(theme.rgba(theme.ACCENT, 50)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(q, 20, 20)
            if st == "active":
                ph = (t * 1.5) % 1.0
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(255, 255, 255, int(255 * (1 - ph))), 2))
                p.drawEllipse(q, MARKER_R + 1 + ph * 16, MARKER_R + 1 + ph * 16)

            outside = math.hypot(w.x, w.y) > fence
            if st == "done":
                fill, edge, txt, glyph = theme.OK, theme.OK, QColor(0, 0, 0), "✓"
            elif st == "active":
                fill, edge, txt, glyph = QColor(255, 255, 255), QColor(255, 255, 255), QColor(0, 0, 0), str(i)
            elif sel:
                fill, edge, txt, glyph = theme.ACCENT, QColor(255, 255, 255), QColor(0, 0, 0), str(i) if i else "H"
            elif i == 0 and not self.show_progress:
                fill, edge, txt, glyph = theme.OK, theme.OK, QColor(0, 0, 0), "H"
            else:
                fill, edge, txt, glyph = QColor(11, 22, 32), theme.ACCENT, theme.ACCENT, str(i) if i else "H"
            if outside:
                edge = theme.ALERT
            p.setBrush(QBrush(fill))
            p.setPen(QPen(edge, 2))
            p.drawEllipse(q, MARKER_R, MARKER_R)
            p.setPen(QPen(txt))
            p.setFont(QFont(theme.FONT_MONO, 8, QFont.Weight.Bold))
            p.drawText(QRectF(q.x() - MARKER_R, q.y() - MARKER_R, MARKER_R * 2, MARKER_R * 2),
                       Qt.AlignmentFlag.AlignCenter, glyph)
            if self.labels:
                p.setFont(QFont(theme.FONT_MONO, 7))
                p.setPen(QPen(theme.rgba(theme.TEXT, 210)))
                extra = f" {w.alt / 100:.1f}m" if w.cmd in ("GO", "TAKEOFF") else f" {w.param}" if w.param else ""
                p.drawText(QPointF(q.x() + MARKER_R + 4, q.y() + 4), f"{w.cmd}{extra}")

    def _draw_drone(self, p: QPainter):
        tr = self.pose.trail
        if len(tr) > 1:
            path = QPainterPath(self._w2s(*tr[0]))
            for pt in tr[1:]:
                path.lineTo(self._w2s(*pt))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, 90), 1.4))
            p.drawPath(path)

        d = self._w2s(self.pose.x, self.pose.y)
        p.save()
        p.translate(d)
        p.rotate(self.pose.yaw)
        grad = QLinearGradient(0, 0, 0, -90)
        grad.setColorAt(0, theme.rgba(theme.ACCENT, 100))
        grad.setColorAt(1, theme.rgba(theme.ACCENT, 0))
        cone = QPainterPath()
        cone.moveTo(0, 0)
        cone.lineTo(-38, -90)
        cone.lineTo(38, -90)
        cone.closeSubpath()
        p.fillPath(cone, QBrush(grad))
        ico = QPainterPath()
        ico.moveTo(0, -11)
        ico.lineTo(8, 9)
        ico.lineTo(0, 5)
        ico.lineTo(-8, 9)
        ico.closeSubpath()
        p.setBrush(QBrush(QColor(255, 255, 255)))
        p.setPen(QPen(theme.ACCENT, 1.2))
        p.drawPath(ico)
        p.restore()

    def _draw_overlay(self, p: QPainter, W: int, H: int):
        p.setFont(QFont(theme.FONT_MONO, 7))
        p.setPen(QPen(theme.rgba(theme.TEXT, 120)))
        p.drawText(QPointF(10, H - 18), "LOCAL FRAME · NO GPS · DEAD-RECKONING (VPS+IMU)")
        # scale bar
        for cm in (1000, 500, 200, 100, 50):
            if cm * self._ppc <= 110:
                px = cm * self._ppc
                p.setPen(QPen(theme.ACCENT, 2))
                p.drawLine(QPointF(W - 20 - px, H - 16), QPointF(W - 20, H - 16))
                p.drawText(QPointF(W - 20 - px, H - 22), f"{cm / 100:g} m")
                break
        p.setPen(QPen(theme.ACCENT))
        p.setFont(QFont(theme.FONT_MONO, 8, QFont.Weight.Bold))
        p.drawText(QPointF(W - 36, 20), "N ▲")
        if self._mouse_world and self.editable:
            x, y = self._mouse_world
            p.setFont(QFont(theme.FONT_MONO, 8))
            p.setPen(QPen(theme.TEXT))
            p.drawText(QPointF(10, 18), f"X {x / 100:+.2f} m   Y {y / 100:+.2f} m")
        if self.live and self.pose is not None:
            p.setFont(QFont(theme.FONT_MONO, 8))
            p.setPen(QPen(theme.rgba(theme.TEXT, 200)))
            if not self.editable:
                p.drawText(QPointF(10, 18), f"POS {self.pose.x / 100:+.2f}, {self.pose.y / 100:+.2f} m   HDG {self.pose.yaw % 360:03.0f}°")
