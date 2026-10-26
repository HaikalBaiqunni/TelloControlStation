"""
src/ui/widgets/flight_log.py
Modern Sci-Fi / Tactical Glass Flight Log Panel.

Features:
  - Chamfered tech-cut corners (angled 45° cuts)
  - Glassmorphic translucent dark emerald backdrop
  - Modern 'Bahnschrift' aerospace typography
  - Color-coded tactical transmission badges ([OK], [WARN], [CRIT])
  - Sleek top header strip with status pulse LED
"""

from typing import List, Tuple
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import QWidget

from src.ui import theme

HUD_GREEN     = theme.ACCENT
HUD_GREEN_DIM = theme.rgba(theme.ACCENT, 0x88)
HUD_GLASS_BG  = theme.GLASS_BG                   # Frosted glass
HUD_BORDER    = theme.GLASS_BORDER
HUD_HEADER_BG = QColor(0x0d, 0x1c, 0x2a, 0x99)

LOG_OK   = theme.OK
LOG_WARN = theme.WARN
LOG_ERR  = theme.ALERT


class FlightLogPanel(QWidget):
    """
    Modern aerospace glass flight log HUD card.
    """

    MAX_VISIBLE = 7
    MAX_STORED  = 200

    def __init__(self, parent=None, width: int = 330, height: int = 145):
        super().__init__(parent)
        if width and height:
            self.setFixedSize(width, height)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._entries: List[Tuple[str, str, str]] = []

    def add_entry(self, ts: str, msg: str, level: str = 'ok'):
        self._entries.append((ts, msg, level))
        if len(self._entries) > self.MAX_STORED:
            self._entries.pop(0)
        self.update()

    def clear(self):
        self._entries.clear()
        self.update()

    def _draw_chamfered_rect(self, painter: QPainter, rect: QRectF, cut: float = 8.0) -> QPainterPath:
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
        card_path = self._draw_chamfered_rect(painter, card_rect, cut)

        # 1. Glass background
        painter.fillPath(card_path, QBrush(HUD_GLASS_BG))

        # 2. Border
        painter.setPen(QPen(HUD_BORDER, 1.2))
        painter.drawPath(card_path)

        # 3. Header bar
        header_h = 24.0
        header_path = QPainterPath()
        header_path.moveTo(cut, 0.5)
        header_path.lineTo(W - cut, 0.5)
        header_path.lineTo(W - 1.0, cut)
        header_path.lineTo(W - 1.0, header_h)
        header_path.lineTo(0.5, header_h)
        header_path.lineTo(0.5, cut)
        header_path.closeSubpath()
        painter.fillPath(header_path, QBrush(HUD_HEADER_BG))
        painter.setPen(QPen(QColor(0x33, 0xaa, 0x66, 0x66), 1.0))
        painter.drawLine(QPointF(0.5, header_h), QPointF(W - 1.0, header_h))

        # Header Title
        painter.setFont(QFont("Bahnschrift", 9, QFont.Weight.DemiBold))
        painter.setPen(QPen(HUD_GREEN, 1.0))
        painter.drawText(QPointF(10, 16), "SYS // TELEMETRY & COMMS LOG")

        # Top-right live status dot
        painter.setBrush(QBrush(HUD_GREEN))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(W - 16, 12), 3, 3)

        # 4. Log Entries
        avail_h = H - header_h - 8
        rows = self.MAX_VISIBLE if self.minimumHeight() == self.maximumHeight() else max(3, int(avail_h // 20))
        visible = self._entries[-rows:]
        start_y = header_h + 4
        line_h = avail_h / max(1, rows)

        font_time = QFont("Consolas", 8)
        font_msg  = QFont("Bahnschrift", 9)

        for i, (ts, msg, level) in enumerate(visible):
            row_y = start_y + i * line_h + line_h * 0.75

            # Timestamp badge
            painter.setFont(font_time)
            painter.setPen(QPen(QColor(0x40, 0x88, 0x60), 1))
            painter.drawText(QPointF(10, row_y), ts)

            # Badge pill tag ([OK], [WARN], [CRIT])
            tag_color = LOG_OK if level == 'ok' else (LOG_WARN if level == 'warn' else LOG_ERR)
            tag_text  = "OK" if level == 'ok' else ("WRN" if level == 'warn' else "ERR")

            # Draw tiny badge
            badge_x = 64
            painter.setPen(QPen(tag_color, 0.8))
            painter.setFont(QFont("Bahnschrift", 7, QFont.Weight.Bold))
            painter.drawText(QPointF(badge_x, row_y), f"[{tag_text}]")

            # Message body
            painter.setFont(font_msg)
            painter.setPen(QPen(tag_color if level != 'ok' else QColor(0xd0, 0xff, 0xe0), 1))
            fm = painter.fontMetrics()
            elided = fm.elidedText(msg, Qt.TextElideMode.ElideRight, int(W - 110))
            painter.drawText(QPointF(badge_x + 36, row_y), elided)
