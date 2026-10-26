"""
src/ui/widgets/sparkline_widget.py
Rolling flight-data trace card (speed, altitude, attitude).

Renders real-time telemetry curves with an optional translucent chamfered glass frame.
Set framed=False to embed it inside another panel (e.g. the FLIGHT DATA glass card).
"""

from collections import deque
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import QWidget

from src.ui import theme

HUD_GREEN     = theme.ACCENT
HUD_CYAN      = theme.ACCENT
HUD_AMBER     = theme.WARN
HUD_GLASS_BG  = theme.GLASS_BG                       # Translucent glass
HUD_BORDER    = theme.GLASS_BORDER
HUD_GRID      = QColor(0xff, 0xff, 0xff, 0x16)


class SparklineSeries:
    def __init__(self, name: str, color: QColor, max_len: int = 60, min_val: float = -30.0, max_val: float = 30.0):
        self.name = name
        self.color = color
        self.min_val = min_val
        self.max_val = max_val
        self.data: deque = deque(maxlen=max_len)
        for _ in range(max_len):
            self.data.append(0.0)

    def push(self, val: float):
        self.data.append(val)


class SparklineCard(QWidget):
    """
    Floating chamfered glass card displaying rolling telemetry sparklines.
    """

    def __init__(self, title: str, parent=None, width: Optional[int] = 180, height: Optional[int] = 75,
                 framed: bool = True):
        super().__init__(parent)
        if width and height:
            self.setFixedSize(width, height)
        else:
            self.setMinimumHeight(60)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self._framed = framed
        self._title = title
        self._series: List[SparklineSeries] = []
        self._curr_readouts: List[Tuple[str, str, QColor]] = []

    def add_series(self, name: str, color: QColor, min_val: float, max_val: float, max_len: int = 60):
        s = SparklineSeries(name, color, max_len, min_val, max_val)
        self._series.append(s)
        return s

    def update_values(self, values: List[float], readouts: Optional[List[Tuple[str, str, QColor]]] = None):
        for i, val in enumerate(values):
            if i < len(self._series):
                self._series[i].push(val)

        if readouts is not None:
            self._curr_readouts = readouts
        self.update()

    def _draw_chamfered(self, p: QPainter, rect: QRectF, cut: float = 6.0) -> QPainterPath:
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
        cut = 6.0

        if self._framed:
            card_rect = QRectF(0.5, 0.5, W - 1.0, H - 1.0)
            card_path = self._draw_chamfered(painter, card_rect, cut)

            # 1. Glass backdrop & frame
            painter.fillPath(card_path, QBrush(HUD_GLASS_BG))
            painter.setPen(QPen(HUD_BORDER, 1.0))
            painter.drawPath(card_path)

            # 2. Header title
            painter.setFont(QFont("Bahnschrift", 8, QFont.Weight.DemiBold))
            painter.setPen(QPen(HUD_GREEN, 1.0))
            painter.drawText(QPointF(8, 13), self._title)
        header_h = 18.0 if self._framed else 14.0

        # Readouts in top-right
        rx = W - 8.0
        painter.setFont(QFont("Bahnschrift", 8, QFont.Weight.Bold))
        for name, txt, col in reversed(self._curr_readouts):
            full_txt = f"{name}:{txt} " if name else f"{txt} "
            tw = painter.fontMetrics().horizontalAdvance(full_txt)
            rx -= tw
            painter.setPen(QPen(col, 1.0))
            painter.drawText(QPointF(rx, 11 if not self._framed else 13), full_txt)

        # 3. Waveform Chart Grid Area
        pad_x = 8.0 if self._framed else 2.0
        pad_y = header_h + 2.0
        plot_w = W - pad_x * 2.0
        plot_h = H - pad_y - 6.0

        # Background grid ticks
        painter.setPen(QPen(HUD_GRID, 0.8))
        painter.drawLine(QPointF(pad_x, pad_y + plot_h / 2), QPointF(pad_x + plot_w, pad_y + plot_h / 2))
        painter.drawLine(QPointF(pad_x + plot_w / 2, pad_y), QPointF(pad_x + plot_w / 2, pad_y + plot_h))

        # 4. Draw Series Waveforms
        for s in self._series:
            data = list(s.data)
            n = len(data)
            if n < 2:
                continue

            painter.setPen(QPen(s.color, 1.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)     # the previous series' head dot left a brush set
            path = QPainterPath()

            span = s.max_val - s.min_val if s.max_val != s.min_val else 1.0

            for i, val in enumerate(data):
                px = pad_x + (i / (n - 1)) * plot_w
                norm = (val - s.min_val) / span
                py = (pad_y + plot_h) - max(0.0, min(1.0, norm)) * plot_h

                if i == 0:
                    path.moveTo(px, py)
                else:
                    path.lineTo(px, py)

            painter.drawPath(path)

            # Glowing head dot on current sample
            last_norm = (data[-1] - s.min_val) / span
            last_x = pad_x + plot_w
            last_y = (pad_y + plot_h) - max(0.0, min(1.0, last_norm)) * plot_h
            painter.setBrush(QBrush(s.color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(last_x - 1, last_y), 2.5, 2.5)
