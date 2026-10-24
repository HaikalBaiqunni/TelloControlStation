"""
src/ui/widgets/tactical_radar.py
Modern Aerospace Glass Tactical Radar & Mission Planner Card.

Features:
  - Chamfered tech glass frame with glowing accents
  - Phosphor range rings with degree ticks
  - Live flight path breadcrumbs (cyan vector trail)
  - Interactive Click-to-add Waypoints with dashed tactical paths
  - Modern sleek pill action buttons ([✕ CLR], [± SCALE], [▶ ENGAGE (N)])
  - Real-time coordinate readouts (Bahnschrift typography)
"""

import math
import time
from typing import List, Tuple

from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QMouseEvent,
)
from PySide6.QtWidgets import QWidget


HUD_GREEN     = QColor(0x55, 0xff, 0x99)
HUD_GREEN_DIM = QColor(0x28, 0x77, 0x44, 0x88)
HUD_GRID      = QColor(0x18, 0x55, 0x30, 0x77)
HUD_GLASS_BG  = QColor(0x06, 0x16, 0x0e, 0xc8)
HUD_BORDER    = QColor(0x33, 0xbb, 0x66, 0x99)
HUD_CONE      = QColor(0x55, 0xff, 0x99, 0x1c)
HUD_TRAIL     = QColor(0x00, 0xf0, 0xff, 0xdd)    # Cyan glow trail
WP_COLOR      = QColor(0xff, 0xd0, 0x33)          # Tactical amber waypoints
WP_LINE       = QColor(0xff, 0xd0, 0x33, 0xaa)


class TacticalRadarWidget(QWidget):
    """
    Modern glass tactical radar card with click-to-plot waypoint missions.
    """

    waypoint_added    = Signal(int, float, float)
    execute_mission   = Signal(list)
    clear_waypoints   = Signal()

    def __init__(self, parent=None, size: int = 220):
        super().__init__(parent)
        self.setFixedSize(size, size + 10)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self._scale_m: float = 3.0    # 3 meters range
        self._drone_x: float = 0.0    # cm
        self._drone_y: float = 0.0    # cm
        self._yaw: float     = 0.0    # deg

        self._trajectory: List[Tuple[float, float]] = [(0.0, 0.0)]
        self._waypoints:  List[Tuple[float, float]] = []
        self._last_time = time.time()

    def update_pose(self, vx_cms: float, vy_cms: float, yaw_deg: float):
        now = time.time()
        dt = min(now - self._last_time, 0.2)
        self._last_time = now

        self._yaw = yaw_deg
        rad = math.radians(yaw_deg)
        dx = (vx_cms * math.sin(rad) + vy_cms * math.cos(rad)) * dt
        dy = (vx_cms * math.cos(rad) - vy_cms * math.sin(rad)) * dt

        self._drone_x += dx
        self._drone_y += dy

        if self._trajectory:
            lx, ly = self._trajectory[-1]
            if (self._drone_x - lx) ** 2 + (self._drone_y - ly) ** 2 > 25:
                self._trajectory.append((self._drone_x, self._drone_y))
                if len(self._trajectory) > 200:
                    self._trajectory.pop(0)

        self.update()

    def add_waypoint(self, x_cm: float, y_cm: float):
        self._waypoints.append((x_cm, y_cm))
        self.waypoint_added.emit(len(self._waypoints), x_cm, y_cm)
        self.update()

    def clear(self):
        self._waypoints.clear()
        self.clear_waypoints.emit()
        self.update()

    def reset_origin(self):
        self._drone_x = 0.0
        self._drone_y = 0.0
        self._trajectory = [(0.0, 0.0)]
        self._waypoints.clear()
        self.update()

    def toggle_zoom(self):
        scales = [2.0, 3.0, 5.0, 10.0]
        curr_idx = scales.index(self._scale_m) if self._scale_m in scales else 0
        self._scale_m = scales[(curr_idx + 1) % len(scales)]
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        W = float(self.width())
        H = float(self.height())
        btn_y = H - 30.0

        x = event.position().x()
        y = event.position().y()

        if event.button() == Qt.MouseButton.LeftButton:
            # Check bottom action buttons
            if y >= btn_y:
                if x < 62:
                    self.clear()
                elif x < 126:
                    self.toggle_zoom()
                else:
                    self.execute_mission.emit(list(self._waypoints))
                return

            # Clicked on radar map -> add waypoint
            grid_h = btn_y - 24.0
            cx = W / 2.0
            cy = 24.0 + grid_h / 2.0
            r_px = min(cx, grid_h / 2.0) - 8.0
            px_per_cm = r_px / (self._scale_m * 100.0)

            dx_cm = (x - cx) / px_per_cm
            dy_cm = -(y - cy) / px_per_cm

            self.add_waypoint(round(dx_cm, 1), round(dy_cm, 1))

        elif event.button() == Qt.MouseButton.RightButton:
            if self._waypoints:
                self._waypoints.pop()
                self.update()

    def _draw_chamfered(self, p: QPainter, rect: QRectF, cut: float = 10.0) -> QPainterPath:
        path = QPainterPath()
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        path.moveTo(x + cut, y)
        path.lineTo(x + w - cut, y)
        path.lineTo(x + w, y + cut)
        path.lineTo(x + w, y + h - cut)
        path.lineTo(x + w - cut, y + h)
        path.lineTo(x + cut, y + h)
        path.lineTo(x, y + h - cut)
        path.lineTo(x, y + cut)
        path.closeSubpath()
        return path

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        W = float(self.width())
        H = float(self.height())
        cut = 10.0

        card_rect = QRectF(0.5, 0.5, W - 1.0, H - 1.0)
        card_path = self._draw_chamfered(painter, card_rect, cut)

        # 1. Glass backdrop & tech frame
        painter.fillPath(card_path, QBrush(HUD_GLASS_BG))
        painter.setPen(QPen(HUD_BORDER, 1.2))
        painter.drawPath(card_path)

        # 2. Modern Header Bar
        header_h = 24.0
        painter.setFont(QFont("Bahnschrift", 9, QFont.Weight.DemiBold))
        painter.setPen(QPen(HUD_GREEN, 1.0))
        painter.drawText(QPointF(10, 16), "RADAR // TACTICAL MAP")

        # Telemetry coord readout
        painter.setFont(QFont("Consolas", 8))
        painter.setPen(QPen(QColor(0x70, 0xcc, 0x90), 1.0))
        pos_txt = f"{self._drone_x:+.0f},{self._drone_y:+.0f}cm"
        painter.drawText(QPointF(W - 85, 16), pos_txt)

        painter.setPen(QPen(QColor(0x33, 0xaa, 0x66, 0x44), 1.0))
        painter.drawLine(QPointF(0.5, header_h), QPointF(W - 1.0, header_h))

        # 3. Radar Display Zone
        btn_y = H - 30.0
        grid_h = btn_y - header_h
        cx = W / 2.0
        cy = header_h + grid_h / 2.0
        r_px = min(cx, grid_h / 2.0) - 8.0

        # Range rings
        painter.setPen(QPen(HUD_GRID, 1.0))
        for frac in (0.33, 0.66, 1.0):
            painter.drawEllipse(QPointF(cx, cy), r_px * frac, r_px * frac)

        # Axis crosshairs
        painter.drawLine(QPointF(cx - r_px, cy), QPointF(cx + r_px, cy))
        painter.drawLine(QPointF(cx, cy - r_px), QPointF(cx, cy + r_px))

        # 4. Heading Field of View Cone
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._yaw)
        cone = QPainterPath()
        cone.moveTo(0, 0)
        cone_len = r_px * 0.98
        half_fov = math.radians(35)
        cone.lineTo(-cone_len * math.sin(half_fov), -cone_len * math.cos(half_fov))
        cone.arcTo(QRectF(-cone_len, -cone_len, cone_len * 2, cone_len * 2), 90 + 35, -70)
        cone.closeSubpath()
        painter.fillPath(cone, QBrush(HUD_CONE))
        painter.restore()

        px_per_cm = r_px / (self._scale_m * 100.0)

        # 5. Breadcrumb Trajectory Path
        if len(self._trajectory) > 1:
            painter.setPen(QPen(HUD_TRAIL, 1.3, Qt.PenStyle.DotLine))
            trail_path = QPainterPath()
            first = True
            for tx, ty in self._trajectory:
                sx = cx + tx * px_per_cm
                sy = cy - ty * px_per_cm
                if first:
                    trail_path.moveTo(sx, sy)
                    first = False
                else:
                    trail_path.lineTo(sx, sy)
            painter.drawPath(trail_path)

        # 6. Waypoints and connecting paths
        if self._waypoints:
            painter.setPen(QPen(WP_LINE, 1.5, Qt.PenStyle.DashLine))
            wp_path = QPainterPath()
            wp_path.moveTo(cx + self._drone_x * px_per_cm, cy - self._drone_y * px_per_cm)
            for wx, wy in self._waypoints:
                wp_path.lineTo(cx + wx * px_per_cm, cy - wy * px_per_cm)
            painter.drawPath(wp_path)

            for i, (wx, wy) in enumerate(self._waypoints):
                sx = cx + wx * px_per_cm
                sy = cy - wy * px_per_cm

                # Waypoint glow node
                painter.setBrush(QBrush(QColor(0x28, 0x22, 0x05, 0xf0)))
                painter.setPen(QPen(WP_COLOR, 1.5))
                painter.drawEllipse(QPointF(sx, sy), 8, 8)

                painter.setFont(QFont("Bahnschrift", 8, QFont.Weight.Bold))
                painter.drawText(QRectF(sx - 8, sy - 8, 16, 16),
                                 Qt.AlignmentFlag.AlignCenter, str(i + 1))

        # 7. Drone Triangle Icon
        dsx = cx + self._drone_x * px_per_cm
        dsy = cy - self._drone_y * px_per_cm
        painter.save()
        painter.translate(dsx, dsy)
        painter.rotate(self._yaw)
        tri = QPainterPath()
        tri.moveTo(0, -9)
        tri.lineTo(-6, 7)
        tri.lineTo(0, 4)
        tri.lineTo(6, 7)
        tri.closeSubpath()
        painter.setBrush(QBrush(HUD_GREEN))
        painter.setPen(QPen(QColor(0xff, 0xff, 0xff), 1.2))
        painter.drawPath(tri)
        painter.restore()

        # 8. Modern Action Buttons at Bottom
        painter.setPen(QPen(QColor(0x33, 0xaa, 0x66, 0x44), 1.0))
        painter.drawLine(QPointF(0.5, btn_y), QPointF(W - 1.0, btn_y))

        # Button 1: [✕ CLR]
        b1_rect = QRectF(6, btn_y + 4, 52, 22)
        b1_path = self._draw_chamfered(painter, b1_rect, 4.0)
        painter.fillPath(b1_path, QBrush(QColor(0x28, 0x0a, 0x10, 0xcc)))
        painter.setPen(QPen(QColor(0xff, 0x55, 0x66), 1.0))
        painter.drawPath(b1_path)
        painter.setFont(QFont("Bahnschrift", 8, QFont.Weight.DemiBold))
        painter.drawText(b1_rect, Qt.AlignmentFlag.AlignCenter, "✕ CLR")

        # Button 2: [± SCALE]
        b2_rect = QRectF(62, btn_y + 4, 58, 22)
        b2_path = self._draw_chamfered(painter, b2_rect, 4.0)
        painter.fillPath(b2_path, QBrush(QColor(0x0a, 0x24, 0x16, 0xcc)))
        painter.setPen(QPen(HUD_GREEN, 1.0))
        painter.drawPath(b2_path)
        painter.drawText(b2_rect, Qt.AlignmentFlag.AlignCenter, f"±{self._scale_m:.0f}m")

        # Button 3: [▶ ENGAGE]
        n_wp = len(self._waypoints)
        b3_rect = QRectF(124, btn_y + 4, W - 130, 22)
        b3_path = self._draw_chamfered(painter, b3_rect, 4.0)
        engage_bg = QColor(0x30, 0x28, 0x05, 0xdd) if n_wp > 0 else QColor(0x0a, 0x1f, 0x14, 0xaa)
        engage_col = WP_COLOR if n_wp > 0 else QColor(0x40, 0x88, 0x60)
        painter.fillPath(b3_path, QBrush(engage_bg))
        painter.setPen(QPen(engage_col, 1.2 if n_wp > 0 else 0.8))
        painter.drawPath(b3_path)
        b3_txt = f"▶ EXEC({n_wp})" if n_wp > 0 else "TAP GRID"
        painter.drawText(b3_rect, Qt.AlignmentFlag.AlignCenter, b3_txt)
