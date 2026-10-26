"""
main.py — Tello Control Station entry point.

Usage:
    python main.py

Requirements:
    pip install PySide6 opencv-python numpy
"""

import sys
import os

# Ensure the project root is on the path so 'src.*' imports resolve correctly
sys.path.insert(0, os.path.dirname(__file__))

# ── Suppress noisy FFmpeg / OpenCV H.264 decoder warnings ────────────────────
# The Tello stream produces harmless "non-existing PPS" / "decode_slice_header"
# messages on every startup until the decoder receives its first keyframe.
# Setting OPENCV_FFMPEG_LOGLEVEL to quiet suppresses them without hiding real errors.
os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "quiet")
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from src.ui.main_window import MainWindow


def main():
    # High-DPI support (PySide6 auto-enables on Qt6, but be explicit)
    os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')

    app = QApplication(sys.argv)
    app.setApplicationName('Tello Control Station')
    app.setApplicationVersion('1.0.0')
    app.setOrganizationName('TelloCS')

    # App-wide dark palette hint (fallback for OS widgets)
    app.setStyle('Fusion')

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
