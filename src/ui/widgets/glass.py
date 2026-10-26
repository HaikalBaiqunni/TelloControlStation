"""
src/ui/widgets/glass.py
GlassPanel — translucent glass card with glowing corner brackets and a title header.
"""

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QVBoxLayout

from src.ui import theme

HEADER_H = 26


class GlassPanel(QFrame):
    """Card with an optional header. Put content into `self.body` (a QVBoxLayout)."""

    def __init__(self, title: str = "", subtitle: str = "", parent=None, radius: float = 12.0):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._title = title
        self._subtitle = subtitle
        self._radius = radius
        top = HEADER_H if title else 8
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(10, top, 10, 10)
        self.body.setSpacing(6)

    def set_title(self, title: str):
        self._title = title
        self.update()

    def set_subtitle(self, text: str):
        if text != self._subtitle:
            self._subtitle = text
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = float(self.width()), float(self.height())
        r = QRectF(0.5, 0.5, W - 1, H - 1)

        p.setBrush(QBrush(theme.GLASS_BG))
        p.setPen(QPen(theme.GLASS_BORDER, 1.0))
        p.drawRoundedRect(r, self._radius, self._radius)

        # corner brackets (top-left / bottom-right)
        p.setPen(QPen(theme.ACCENT, 2.0))
        c = 12.0
        p.drawLine(QPointF(1, 1 + c), QPointF(1, 1 + self._radius * 0.4))
        p.drawLine(QPointF(1 + self._radius * 0.4, 1), QPointF(1 + c, 1))
        p.drawLine(QPointF(W - 1, H - 1 - c), QPointF(W - 1, H - 1 - self._radius * 0.4))
        p.drawLine(QPointF(W - 1 - self._radius * 0.4, H - 1), QPointF(W - 1 - c, H - 1))

        if self._title:
            f = QFont(theme.FONT_UI, 8, QFont.Weight.DemiBold)
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.8)
            p.setFont(f)
            p.setPen(QPen(theme.ACCENT))
            p.drawText(QRectF(12, 0, W - 24, HEADER_H + 2),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._title.upper())
            if self._subtitle:
                p.setFont(QFont(theme.FONT_MONO, 8))
                p.setPen(QPen(theme.MUTED))
                p.drawText(QRectF(12, 0, W - 24, HEADER_H + 2),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self._subtitle)
