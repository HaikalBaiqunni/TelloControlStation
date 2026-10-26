"""
src/ui/theme.py
Shared palette, fonts and global stylesheet for the glass-cockpit UI (design "D").
"""

from PySide6.QtGui import QColor

FONT_UI   = "Bahnschrift"
FONT_MONO = "Consolas"

ACCENT = QColor(0x27, 0xf3, 0xff)      # primary cyan
OK     = QColor(0x3d, 0xff, 0x9a)      # completed / healthy
WARN   = QColor(0xff, 0xb0, 0x20)      # caution / objects
ALERT  = QColor(0xff, 0x3b, 0x5c)      # alert / geofence
MUTED  = QColor(0x6f, 0x93, 0xa3)
TEXT   = QColor(0xd6, 0xf6, 0xff)
MAP_BG = QColor(0x08, 0x11, 0x1a)


def rgba(c: QColor, a: int) -> QColor:
    """Return a copy of `c` with alpha `a` (0-255)."""
    out = QColor(c)
    out.setAlpha(a)
    return out


GLASS_BG     = QColor(10, 18, 28, 150)
GLASS_BORDER = rgba(ACCENT, 72)

# Command colours used in the waypoint table / status list
CMD_COLORS = {
    "TAKEOFF": OK,
    "LAND":    ALERT,
    "ROTATE":  WARN,
    "FLIP":    WARN,
    "HOVER":   WARN,
    "GO":      ACCENT,
}

APP_STYLE = f"""
QMainWindow {{ background: #05080d; }}
QLabel {{ background: transparent; color: {TEXT.name()};
          font-family: "{FONT_UI}", "Segoe UI", sans-serif; font-size: 11px; }}
QLabel#muted {{ color: {MUTED.name()}; font-size: 9px; letter-spacing: 1.5px; }}
QLabel#big   {{ color: {ACCENT.name()}; font-family: "{FONT_MONO}"; font-size: 26px; font-weight: 600; }}
QLabel#chip  {{ border: 1px solid rgba(39,243,255,72); border-radius: 11px; padding: 2px 10px;
                font-family: "{FONT_MONO}"; font-size: 11px; }}
QLabel#kvv   {{ font-family: "{FONT_MONO}"; font-size: 15px; }}
QLabel#logo  {{ color: {ACCENT.name()}; font-size: 13px; font-weight: 700; letter-spacing: 3px; }}

QFrame#kv {{ background: rgba(255,255,255,12); border-radius: 8px; }}

QPushButton {{
    background: rgba(39,243,255,20); color: {ACCENT.name()};
    border: 1px solid rgba(39,243,255,80); border-radius: 7px; padding: 7px 12px;
    font-family: "{FONT_UI}", sans-serif; font-size: 11px; font-weight: 600; letter-spacing: 1px;
}}
QPushButton:hover   {{ background: {ACCENT.name()}; color: #001018; }}
QPushButton:pressed {{ background: #ffffff; color: #001018; }}
QPushButton:disabled {{ color: #3d5a63; border-color: rgba(39,243,255,30); background: rgba(39,243,255,8); }}
QPushButton#primary {{ background: {ACCENT.name()}; color: #001018; }}
QPushButton#primary:hover {{ background: #ffffff; }}
QPushButton#ok      {{ color: {OK.name()}; border-color: rgba(61,255,154,120); background: rgba(61,255,154,22); }}
QPushButton#ok:hover {{ background: {OK.name()}; color: #001018; }}
QPushButton#warn    {{ color: {WARN.name()}; border-color: rgba(255,176,32,120); background: rgba(255,176,32,22); }}
QPushButton#warn:hover {{ background: {WARN.name()}; color: #001018; }}
QPushButton#danger  {{ color: {ALERT.name()}; border-color: rgba(255,59,92,130); background: rgba(255,59,92,22); }}
QPushButton#danger:hover {{ background: {ALERT.name()}; color: #ffffff; }}
QPushButton#tab {{ background: transparent; border: none; border-radius: 0; color: {MUTED.name()};
                   padding: 12px 12px; font-size: 10px; letter-spacing: 2px; }}
QPushButton#tab:hover {{ color: #ffffff; background: transparent; }}
QPushButton#tab:checked {{ color: #ffffff; border-bottom: 2px solid {ACCENT.name()}; }}
QPushButton#tool {{ text-align: left; }}

QDoubleSpinBox, QSpinBox, QComboBox {{
    background: rgba(8,17,26,220); color: {TEXT.name()}; border: 1px solid rgba(39,243,255,60);
    border-radius: 5px; padding: 2px 6px; font-family: "{FONT_MONO}"; font-size: 11px; }}
QComboBox QAbstractItemView {{ background: #0a1620; color: {TEXT.name()}; selection-background-color: rgba(39,243,255,70); }}

QTableWidget {{
    background: transparent; color: {TEXT.name()}; border: none; gridline-color: transparent;
    font-family: "{FONT_MONO}"; font-size: 11px; selection-background-color: rgba(39,243,255,50);
    selection-color: #ffffff; outline: 0; }}
QTableWidget::item:focus, QTableWidget::item:selected {{ border: none; outline: 0; }}
QTableWidget::item:selected {{ background: rgba(39,243,255,50); border-bottom: 1px solid rgba(255,255,255,13); }}
QTableWidget::item {{ padding: 3px 6px; border-bottom: 1px solid rgba(255,255,255,13); }}
QHeaderView::section {{
    background: rgba(12,22,32,235); color: {MUTED.name()}; border: none;
    border-bottom: 1px solid rgba(39,243,255,72); padding: 4px 6px;
    font-family: "{FONT_UI}"; font-size: 9px; letter-spacing: 1.5px; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: rgba(39,243,255,70); border-radius: 4px; min-height: 20px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QToolTip {{ background: #0a1620; color: {TEXT.name()}; border: 1px solid rgba(39,243,255,100); }}
"""
