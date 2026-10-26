"""
src/ui/widgets/camera_widget.py
Full-bleed FPV camera canvas with corner guides and AI target-lock brackets.
Other widgets are laid out on top of it (see src/ui/pages.py).
"""

from typing import Any, Dict, List, Optional

import numpy as np
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from src.ui import theme


class CameraWidget(QWidget):
    """Draws the video frame, tactical corner guides and AI lock brackets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._detections: List[Dict[str, Any]] = []
        self._ai_enabled: bool = True
        self.setMinimumSize(640, 420)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_frame(self, frame: np.ndarray):
        h, w, ch = frame.shape
        qimg = QImage(frame.data, w, h, ch * w, QImage.Format.Format_BGR888)
        self._pixmap = QPixmap.fromImage(qimg)
        self.update()

    def set_detections(self, detections: List[Dict[str, Any]]):
        self._detections = detections
        self.update()

    def set_ai_enabled(self, enabled: bool):
        self._ai_enabled = enabled
        if not enabled:
            self._detections = []
        self.update()

    def clear_frame(self):
        self._pixmap = None
        self._detections = []
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = float(self.width()), float(self.height())

        # 1. Video canvas / standby
        if self._pixmap:
            scaled = self._pixmap.scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            x = (scaled.width() - self.width()) // 2
            y = (scaled.height() - self.height()) // 2
            p.drawPixmap(0, 0, scaled, x, y, self.width(), self.height())
        else:
            p.fillRect(self.rect(), QBrush(QColor(0x05, 0x08, 0x0d)))
            p.setPen(QPen(theme.rgba(theme.ACCENT, 0x55)))
            p.setFont(QFont(theme.FONT_UI, 20, QFont.Weight.Bold))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "[ HUD STANDBY // NO SENSOR FEED ]")
            p.setFont(QFont(theme.FONT_UI, 10))
            p.setPen(QPen(theme.rgba(theme.ACCENT, 0x40)))
            p.drawText(self.rect().adjusted(0, 48, 0, 0),
                       Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop,
                       "CONNECT DRONE TO ENGAGE OPTICAL & AVIONICS LINK")

        # 2. Soft vignette so the glass panels stay readable on bright video
        from PySide6.QtGui import QRadialGradient
        g = QRadialGradient(QPointF(W / 2, H / 2), max(W, H) * 0.65)
        g.setColorAt(0.55, QColor(0, 0, 0, 0))
        g.setColorAt(1.0, QColor(0, 0, 0, 150))
        p.fillRect(self.rect(), QBrush(g))

        # 3. AI object & person target-lock brackets
        if self._ai_enabled and self._detections:
            for d in self._detections:
                x1n, y1n, x2n, y2n = d["box_norm"]
                is_person = d.get("is_person", False)
                label = d.get("label", "OBJ")
                conf = d.get("conf", 0.0)

                bx1, by1, bx2, by2 = x1n * W, y1n * H, x2n * W, y2n * H
                bw, bh = bx2 - bx1, by2 - by1
                color = theme.ACCENT if is_person else theme.WARN
                p.setPen(QPen(color, 1.8))
                p.setBrush(Qt.BrushStyle.NoBrush)

                c = max(8.0, min(24.0, min(bw, bh) * 0.25))
                for (px, py, sx, sy) in ((bx1, by1, 1, 1), (bx2, by1, -1, 1), (bx1, by2, 1, -1), (bx2, by2, -1, -1)):
                    p.drawLine(QPointF(px, py), QPointF(px + sx * c, py))
                    p.drawLine(QPointF(px, py), QPointF(px, py + sy * c))

                mcx, mcy = bx1 + bw / 2, by1 + bh / 2
                p.setPen(QPen(color, 1.0))
                p.drawLine(QPointF(mcx - 5, mcy), QPointF(mcx + 5, mcy))
                p.drawLine(QPointF(mcx, mcy - 5), QPointF(mcx, mcy + 5))

                tag = f"{'TGT' if is_person else 'OBJ'} // {label.upper()} {int(conf * 100)}%"
                p.setFont(QFont(theme.FONT_UI, 8, QFont.Weight.Bold))
                tw = p.fontMetrics().horizontalAdvance(tag) + 12
                badge = QRectF(bx1, max(10.0, by1 - 18.0), tw, 16.0)
                p.fillRect(badge, QBrush(QColor(0x06, 0x12, 0x1a, 0xd8)))
                p.setPen(QPen(color, 1.0))
                p.drawRect(badge)
                p.drawText(badge, Qt.AlignmentFlag.AlignCenter, tag)
