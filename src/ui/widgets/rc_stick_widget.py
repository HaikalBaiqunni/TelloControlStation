"""
src/ui/widgets/rc_stick_widget.py
Virtual RC joystick visualizer — draws two joystick circles
showing current RC input values.
"""

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import (
    QBrush, QColor, QPainter, QPen, QRadialGradient,
)
from PySide6.QtWidgets import QWidget


from src.ui import theme

C_BG      = QColor(0x08, 0x11, 0x1a, 0xcc)
C_BORDER  = theme.rgba(theme.ACCENT, 0x70)
C_CROSS   = theme.rgba(theme.ACCENT, 0x30)
C_DOT     = theme.ACCENT
C_DOT_GLO = theme.rgba(theme.ACCENT, 0x80)
C_LABEL   = theme.MUTED


class RCStickWidget(QWidget):
    """
    Circular joystick visualizer.

    Update via:
        widget.set_values(x, y)   # x, y in range [-1.0, 1.0]
    """

    def __init__(self, parent=None, size: int = 70, label: str = ''):
        super().__init__(parent)
        self._x = 0.0
        self._y = 0.0
        self._label = label
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_values(self, x: float, y: float):
        """x: left(-1)–right(+1), y: down(-1)–up(+1)"""
        self._x = max(-1.0, min(1.0, x))
        self._y = max(-1.0, min(1.0, y))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        W = self.width()
        H = self.height()
        cx, cy = W / 2.0, H / 2.0
        radius = min(cx, cy) - 2

        # Background circle
        painter.setBrush(QBrush(C_BG))
        painter.setPen(QPen(C_BORDER, 1))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # Crosshair
        painter.setPen(QPen(C_CROSS, 0.5))
        painter.drawLine(QPointF(cx - radius, cy), QPointF(cx + radius, cy))
        painter.drawLine(QPointF(cx, cy - radius), QPointF(cx, cy + radius))

        # Dead-zone circle (optional visual reference)
        dead_r = radius * 0.12
        painter.setPen(QPen(C_CROSS, 0.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), dead_r, dead_r)

        # Stick dot
        travel = radius - 8
        sx = cx + self._x * travel
        sy = cy - self._y * travel          # y flipped (up = positive)

        # Glow effect
        grad = QRadialGradient(QPointF(sx, sy), 10)
        grad.setColorAt(0.0, C_DOT)
        grad.setColorAt(0.6, C_DOT_GLO)
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(sx, sy), 10, 10)

        # Solid center of stick dot
        painter.setBrush(QBrush(C_DOT))
        painter.drawEllipse(QPointF(sx, sy), 5, 5)

        # Label
        if self._label:
            from PySide6.QtGui import QFont
            painter.setPen(QPen(C_LABEL, 1))
            painter.setFont(QFont('Courier New', max(7, int(radius * 0.13))))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                             self._label)
