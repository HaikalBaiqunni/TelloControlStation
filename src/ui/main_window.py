"""
src/ui/main_window.py
Tello Control Station — Modern Aerospace Glass Cockpit & Tactical HUD with AI Vision.

Features:
  - 100% Full-bleed FPV Camera Canopy (Ace Combat Jet Fighter HUD)
  - Real-Time AI Object & Person Detection (YOLOv8 Nano Target Lock Brackets)
  - In-HUD Floating Micro-Sparklines:
      - // SPEED PROFILE
      - // ALT PROFILE
      - // ATTITUDE (Pitch, Roll, and Yaw 3-channel wave telemetry)
  - Chamfered Glass Tactical Radar with Trajectory & Waypoint Mission Planner
  - Floating Glass Avionics Action Deck with Chamfered Tech Buttons
  - Seamless Dual Input (Keyboard + Gamepad with Global Focus Lock)
  - Toggleable AI Targeting ([🎯 AI TRACK: ON/OFF]) & Plots ([📈 PLOTS: ON/OFF])
"""

import math
import sys
import threading
from typing import Optional, List, Dict, Any

import cv2
import numpy as np

from PySide6.QtCore import (
    Qt, QTimer, QSize, QRect, QPoint, QPointF, QRectF, Signal, Slot, QObject, QEvent,
)
from PySide6.QtGui import (
    QColor, QFont, QImage, QKeyEvent, QPainter, QPen, QBrush, QPixmap,
    QResizeEvent, QPainterPath,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel,
    QHBoxLayout, QVBoxLayout, QSizePolicy, QMessageBox,
)

from src.drone.tello_sdk import TelloSDK
from src.drone.video_stream import VideoStreamThread
from src.drone.state_parser import DroneState
from src.drone.mission_planner import MissionPlanner
from src.drone.object_detector import ObjectDetector
from src.input.gamepad_handler import GamepadHandler
from src.ui.widgets.fighter_hud import FighterHUDWidget
from src.ui.widgets.tactical_radar import TacticalRadarWidget
from src.ui.widgets.flight_log import FlightLogPanel
from src.ui.widgets.sparkline_widget import SparklineCard
from src.utils.logger import FlightLogger


# ── Modern Aerospace Glass Palette & Style ─────────────────────────────
HUD_GREEN     = "#55ff99"
HUD_AMBER     = "#ffbb33"
HUD_ALERT     = "#ff4455"
HUD_CYAN      = "#00f0ff"

MODERN_COCKPIT_STYLE = """
QMainWindow, QWidget {
    background: #040906;
    color: #55ff99;
    font-family: "Bahnschrift", "Segoe UI Semibold", sans-serif;
    font-size: 11px;
}

/* Floating Glass Action Deck */
QWidget#action_deck {
    background: rgba(6, 20, 14, 0.86);
    border: 1px solid rgba(51, 187, 102, 0.65);
    border-radius: 8px;
}

/* Modern Tactical Buttons */
QPushButton {
    background: rgba(12, 36, 24, 0.85);
    color: #55ff99;
    border: 1px solid rgba(51, 187, 102, 0.7);
    border-radius: 4px;
    padding: 6px 12px;
    font-family: "Bahnschrift", sans-serif;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.8px;
    text-transform: uppercase;
}

QPushButton:hover {
    background: rgba(40, 110, 68, 0.9);
    border-color: #55ff99;
    color: #ffffff;
}

QPushButton:pressed {
    background: #55ff99;
    color: #040906;
}

QPushButton#btn_takeoff {
    color: #55ff99;
    border: 1px solid #55ff99;
    background: rgba(15, 45, 30, 0.9);
}
QPushButton#btn_takeoff:hover {
    background: #55ff99;
    color: #040906;
}

QPushButton#btn_land {
    color: #ffbb33;
    border: 1px solid #ffbb33;
    background: rgba(45, 35, 10, 0.9);
}
QPushButton#btn_land:hover {
    background: #ffbb33;
    color: #040906;
}

QPushButton#btn_emergency {
    color: #ff4455;
    border: 1.5px solid #ff4455;
    background: rgba(55, 12, 18, 0.9);
    padding: 6px 16px;
    font-weight: 700;
}
QPushButton#btn_emergency:hover {
    background: #ff4455;
    color: #ffffff;
}

/* Glass Status Badges */
QLabel.glass_pod {
    background: rgba(6, 20, 14, 0.84);
    border: 1px solid rgba(51, 187, 102, 0.55);
    border-radius: 6px;
    padding: 5px 12px;
    font-family: "Bahnschrift", sans-serif;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.8px;
    color: #55ff99;
}

QLabel#lbl_mode {
    color: #ffbb33;
    font-family: "Bahnschrift", sans-serif;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.2px;
    padding: 4px 8px;
}
"""


# ══════════════════════════════════════════════════════════════════════
#  Camera background widget with AI Target Lock Overlay
# ══════════════════════════════════════════════════════════════════════

class CameraWidget(QWidget):
    """Draws full-window video, HUD corner guides, and AI Target Lock Brackets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._detections: List[Dict[str, Any]] = []
        self._ai_enabled: bool = True
        self.setMinimumSize(800, 500)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_frame(self, frame: np.ndarray):
        h, w, ch = frame.shape
        bytes_per_line = ch * w
        qimg = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_BGR888)
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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        W = float(self.width())
        H = float(self.height())

        # 1. Video Canvas / Standby
        if self._pixmap:
            scaled = self._pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (scaled.width()  - self.width())  // 2
            y = (scaled.height() - self.height()) // 2
            painter.drawPixmap(0, 0, scaled, x, y, self.width(), self.height())
        else:
            painter.fillRect(self.rect(), QBrush(QColor(0x04, 0x0a, 0x07)))
            painter.setPen(QPen(QColor(0x22, 0x66, 0x3e)))
            painter.setFont(QFont("Bahnschrift", 20, QFont.Weight.Bold))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "[ HUD STANDBY // NO SENSOR FEED ]")
            painter.setFont(QFont("Bahnschrift", 10))
            painter.setPen(QPen(QColor(0x18, 0x48, 0x2c)))
            painter.drawText(
                self.rect().adjusted(0, 48, 0, 0),
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop,
                "CONNECT DRONE TO ENGAGE OPTICAL & AVIONICS LINK",
            )

        # 2. Tactical Corner Target Brackets
        painter.setPen(QPen(QColor(0x55, 0xff, 0x99, 0x55), 1.8))
        bsz = 24.0
        pad = 10.0
        painter.drawLine(QPointF(pad, pad), QPointF(pad + bsz, pad))
        painter.drawLine(QPointF(pad, pad), QPointF(pad, pad + bsz))
        painter.drawLine(QPointF(W - pad, pad), QPointF(W - pad - bsz, pad))
        painter.drawLine(QPointF(W - pad, pad), QPointF(W - pad, pad + bsz))
        painter.drawLine(QPointF(pad, H - pad), QPointF(pad + bsz, H - pad))
        painter.drawLine(QPointF(pad, H - pad), QPointF(pad, H - pad - bsz))
        painter.drawLine(QPointF(W - pad, H - pad), QPointF(W - pad - bsz, H - pad))
        painter.drawLine(QPointF(W - pad, H - pad), QPointF(W - pad, H - pad - bsz))

        # 3. AI Object & Person Target Lock Brackets
        if self._ai_enabled and self._detections:
            for d in self._detections:
                x1_n, y1_n, x2_n, y2_n = d["box_norm"]
                is_person = d.get("is_person", False)
                label     = d.get("label", "OBJ")
                conf      = d.get("conf", 0.0)

                bx1 = x1_n * W
                by1 = y1_n * H
                bx2 = x2_n * W
                by2 = y2_n * H
                bw = bx2 - bx1
                bh = by2 - by1

                # Colors: Persons get Emerald Green/Cyan lock, Objects get Tactical Amber
                color = QColor(0x00, 0xf0, 0xff) if is_person else QColor(0xff, 0xbb, 0x33)
                painter.setPen(QPen(color, 1.8))
                painter.setBrush(Qt.BrushStyle.NoBrush)

                # Corner targeting brackets around detection
                c_len = min(bw, bh) * 0.25
                c_len = max(8.0, min(24.0, c_len))

                # Top-Left
                painter.drawLine(QPointF(bx1, by1), QPointF(bx1 + c_len, by1))
                painter.drawLine(QPointF(bx1, by1), QPointF(bx1, by1 + c_len))
                # Top-Right
                painter.drawLine(QPointF(bx2, by1), QPointF(bx2 - c_len, by1))
                painter.drawLine(QPointF(bx2, by1), QPointF(bx2, by1 + c_len))
                # Bottom-Left
                painter.drawLine(QPointF(bx1, by2), QPointF(bx1 + c_len, by2))
                painter.drawLine(QPointF(bx1, by2), QPointF(bx1, by2 - c_len))
                # Bottom-Right
                painter.drawLine(QPointF(bx2, by2), QPointF(bx2 - c_len, by2))
                painter.drawLine(QPointF(bx2, by2), QPointF(bx2, by2 - c_len))

                # Center Tracking Crosshair
                mcx = bx1 + bw / 2.0
                mcy = by1 + bh / 2.0
                ch_sz = 5.0
                painter.setPen(QPen(color, 1.0))
                painter.drawLine(QPointF(mcx - ch_sz, mcy), QPointF(mcx + ch_sz, mcy))
                painter.drawLine(QPointF(mcx, mcy - ch_sz), QPointF(mcx, mcy + ch_sz))

                # Target Classification Badge Top
                tag_txt = f"{'👤 TGT // ' if is_person else '🎯 OBJ // '}{label} {int(conf * 100)}%"
                painter.setFont(QFont("Bahnschrift", 8, QFont.Weight.Bold))
                tw = painter.fontMetrics().horizontalAdvance(tag_txt) + 12

                badge_rect = QRectF(bx1, max(10.0, by1 - 18.0), tw, 16.0)
                painter.fillRect(badge_rect, QBrush(QColor(0x06, 0x18, 0x10, 0xd8)))
                painter.setPen(QPen(color, 1.0))
                painter.drawRect(badge_rect)
                painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, tag_txt)


# ══════════════════════════════════════════════════════════════════════
#  Global Keyboard Control Filter
# ══════════════════════════════════════════════════════════════════════

class GlobalControlFilter(QObject):
    def __init__(self, main_window):
        super().__init__(main_window)
        self._mw = main_window

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress:
            key_event: QKeyEvent = event
            if not key_event.isAutoRepeat():
                if self._mw.handle_key_down(key_event.key()):
                    return True
        elif event.type() == QEvent.Type.KeyRelease:
            key_event: QKeyEvent = event
            if not key_event.isAutoRepeat():
                if self._mw.handle_key_up(key_event.key()):
                    return True
        return super().eventFilter(watched, event)


# ══════════════════════════════════════════════════════════════════════
#  Main Window
# ══════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """Modern Aerospace Glass Cockpit with AI Vision & 3-Axis Telemetry."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tello Tactical Control Station // Jet Fighter HUD & AI Vision")
        self.setMinimumSize(960, 640)
        self.resize(1280, 720)
        self.setStyleSheet(MODERN_COCKPIT_STYLE)

        # ── Core Subsystems ─────────────────────────────────────────
        self._drone    = TelloSDK(self)
        self._video    = VideoStreamThread(self)
        self._logger   = FlightLogger(max_entries=300)
        self._gamepad  = GamepadHandler(self)
        self._mission  = MissionPlanner(self._drone, self._logger, self)
        self._detector = ObjectDetector(model_path="yolov8n.pt", parent=self)

        self._flying = False
        self._pressed_keys: set = set()
        self._rc_speed = 60
        self._gamepad_rc = (0, 0, 0, 0)
        self._plots_visible = True
        self._ai_enabled    = True

        # ── Build Modern UI ─────────────────────────────────────────
        self._build_ui()
        self._connect_signals()
        self._position_overlays()

        # Global key focus lock
        self._key_filter = GlobalControlFilter(self)
        QApplication.instance().installEventFilter(self._key_filter)

        # ── RC Control Loop (25 Hz) ─────────────────────────────────
        self._rc_timer = QTimer(self)
        self._rc_timer.setInterval(40)
        self._rc_timer.timeout.connect(self._rc_loop_tick)
        self._rc_timer.start()

        self._log("AVIONICS GLASS & AI VISION ONLINE", "ok")
        self._log("Ready for sortie. Establish drone link.", "ok")

    def _build_ui(self):
        # 1. 100% Full-bleed Camera Canopy as Central Widget
        self._cam = CameraWidget(self)
        self.setCentralWidget(self._cam)

        # 2. Modern Fighter Jet HUD Vector Overlay
        self._hud = FighterHUDWidget(self._cam)

        # 3. Modern Tactical Radar & Waypoint Mission Card (Bottom-Left)
        self._radar = TacticalRadarWidget(self._cam, size=220)

        # 4. Modern Glass Flight Log Card (Bottom-Right)
        self._log_panel = FlightLogPanel(self._cam, width=330, height=145)

        # 5. Top-Left Controller Glass Pod
        self._ctrl_badge = QLabel(self._cam)
        self._ctrl_badge.setProperty("class", "glass_pod")
        self._ctrl_badge.setObjectName("ctrl_badge")
        self._ctrl_badge.setText("🎮 NO GAMEPAD // KEYBOARD PILOT")

        # 6. Top-Right Power & Sensor Glass Pod
        self._stats_card = QLabel(self._cam)
        self._stats_card.setProperty("class", "glass_pod")
        self._stats_card.setObjectName("stats_card")
        self._stats_card.setText("BAT: --% | TOF: --cm | TEMP: --°C")

        # ── 7. IN-HUD FLOATING MICRO-SPARKLINES ──────────────────────
        # 7a. Speed Trend Sparkline (under Left Speed Tape)
        self._spark_spd = SparklineCard("// SPEED PROFILE", self._cam, width=175, height=65)
        self._spark_spd.add_series("SPD", QColor(0x55, 0xff, 0x99), min_val=0, max_val=80)

        # 7b. Altitude Profile Sparkline (under Right Altitude Tape)
        self._spark_alt = SparklineCard("// ALT PROFILE", self._cam, width=175, height=65)
        self._spark_alt.add_series("ALT", QColor(0x00, 0xf0, 0xff), min_val=0, max_val=200)

        # 7c. Attitude Card (Pitch, Roll, and Yaw 3-channel wave telemetry!)
        self._spark_att = SparklineCard("// ATTITUDE", self._cam, width=320, height=74)
        self._spark_att.add_series("PITCH", QColor(0x55, 0xff, 0x99), min_val=-35, max_val=35)
        self._spark_att.add_series("ROLL",  QColor(0x00, 0xf0, 0xff), min_val=-35, max_val=35)
        self._spark_att.add_series("YAW",   QColor(0xff, 0xbb, 0x33), min_val=-180, max_val=180)

        # 8. Floating Glass Avionics Action Deck (Bottom-Center)
        self._action_deck = QWidget(self._cam)
        self._action_deck.setObjectName("action_deck")

        deck_layout = QHBoxLayout(self._action_deck)
        deck_layout.setContentsMargins(14, 8, 14, 8)
        deck_layout.setSpacing(8)

        self._btn_connect   = QPushButton("⚡ UPLINK",       self._action_deck)
        self._btn_takeoff   = QPushButton("▲ LAUNCH",       self._action_deck)
        self._btn_land      = QPushButton("▼ RTB LAND",      self._action_deck)
        self._btn_rst_pos   = QPushButton("⌖ RESET HOME",    self._action_deck)
        self._btn_ai        = QPushButton("🎯 AI TRACK: ON", self._action_deck)
        self._btn_plot      = QPushButton("📈 PLOTS: ON",    self._action_deck)
        self._lbl_mode      = QLabel("MODE: STANDBY",        self._action_deck)
        self._btn_emergency = QPushButton("⚠ CUTOFF",        self._action_deck)

        self._btn_takeoff.setObjectName("btn_takeoff")
        self._btn_land.setObjectName("btn_land")
        self._btn_emergency.setObjectName("btn_emergency")
        self._lbl_mode.setObjectName("lbl_mode")

        for btn in (self._btn_connect, self._btn_takeoff, self._btn_land,
                    self._btn_rst_pos, self._btn_ai, self._btn_plot, self._btn_emergency):
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        deck_layout.addWidget(self._btn_connect)
        deck_layout.addWidget(self._btn_takeoff)
        deck_layout.addWidget(self._btn_land)
        deck_layout.addWidget(self._btn_rst_pos)
        deck_layout.addWidget(self._btn_ai)
        deck_layout.addWidget(self._btn_plot)
        deck_layout.addSpacing(4)
        deck_layout.addWidget(self._lbl_mode)
        deck_layout.addSpacing(4)
        deck_layout.addWidget(self._btn_emergency)

    def _connect_signals(self):
        # Buttons
        self._btn_connect.clicked.connect(self._on_connect_clicked)
        self._btn_takeoff.clicked.connect(self._on_takeoff_clicked)
        self._btn_land.clicked.connect(self._on_land_clicked)
        self._btn_emergency.clicked.connect(self._on_emergency_clicked)
        self._btn_rst_pos.clicked.connect(self._radar.reset_origin)
        self._btn_plot.clicked.connect(self._toggle_plots)
        self._btn_ai.clicked.connect(self._toggle_ai)

        # Drone SDK
        self._drone.connected_sig.connect(self._on_drone_connected)
        self._drone.disconnected_sig.connect(self._on_drone_disconnected)
        self._drone.error_sig.connect(self._on_drone_error)
        self._drone.state_received.connect(self._on_state_received)

        # Video
        self._video.frame_ready.connect(self._on_video_frame)
        self._video.stream_error.connect(lambda e: self._log(f"Video: {e}", "err"))
        self._video.stream_started.connect(lambda: self._log("Optical sensor link engaged", "ok"))
        self._video.stream_stopped.connect(self._cam.clear_frame)

        # AI Object Detector
        self._detector.detections_ready.connect(self._cam.set_detections)
        self._detector.model_loaded.connect(lambda ok: self._log("AI YOLOv8 Vision Engine ready", "ok") if ok else self._log("AI Engine failed", "err"))

        # Logger
        self._logger.add_callback(self._log_panel.add_entry)

        # Gamepad
        self._gamepad.rc_changed.connect(self._on_gamepad_rc)
        self._gamepad.takeoff_pressed.connect(self._on_takeoff_clicked)
        self._gamepad.land_pressed.connect(self._on_land_clicked)
        self._gamepad.emergency_pressed.connect(self._on_emergency_clicked)
        self._gamepad.flip_pressed.connect(lambda d: threading.Thread(target=lambda: self._drone.flip(d), daemon=True).start())
        self._gamepad.status_changed.connect(self._on_gamepad_status)

        # Radar & Mission Planner
        self._radar.execute_mission.connect(self._on_execute_mission)
        self._mission.waypoint_reached.connect(lambda wp, x, y: self._log(f"WP{wp} reached: ({x:.0f}, {y:.0f}) cm", "ok"))
        self._mission.mission_finished.connect(lambda ok, msg: self._log(f"Mission: {msg}", "ok" if ok else "warn"))

    def _on_video_frame(self, frame: np.ndarray):
        # 1. Update UI Camera Widget
        self._cam.set_frame(frame)
        # 2. Push frame to async AI Object Detector
        if self._ai_enabled:
            self._detector.push_frame(frame)

    def _toggle_plots(self):
        self._plots_visible = not self._plots_visible
        self._spark_spd.setVisible(self._plots_visible)
        self._spark_alt.setVisible(self._plots_visible)
        self._spark_att.setVisible(self._plots_visible)
        self._btn_plot.setText(f"📈 PLOTS: {'ON' if self._plots_visible else 'OFF'}")

    def _toggle_ai(self):
        self._ai_enabled = not self._ai_enabled
        self._detector.set_enabled(self._ai_enabled)
        self._cam.set_ai_enabled(self._ai_enabled)
        self._btn_ai.setText(f"🎯 AI TRACK: {'ON' if self._ai_enabled else 'OFF'}")
        self._log(f"AI Target Recognition: {'ENABLED' if self._ai_enabled else 'DISABLED'}", "ok" if self._ai_enabled else "warn")

    def _position_overlays(self):
        if not hasattr(self, "_cam"):
            return

        W = self._cam.width()
        H = self._cam.height()
        cx = W // 2
        cy = H // 2

        # 1. Full-screen HUD
        self._hud.setGeometry(0, 0, W, H)

        # 2. Tactical Radar in bottom-left
        rw, rh = self._radar.width(), self._radar.height()
        self._radar.move(16, H - rh - 16)

        # 3. Flight Log in bottom-right
        lw, lh = self._log_panel.width(), self._log_panel.height()
        self._log_panel.move(W - lw - 16, H - lh - 16)

        # 4. Top-Left Controller Pod
        self._ctrl_badge.adjustSize()
        self._ctrl_badge.move(16, 14)

        # 5. Top-Right Power/Sensor Pod
        self._stats_card.adjustSize()
        self._stats_card.move(W - self._stats_card.width() - 16, 14)

        # 6. Floating Action Deck in bottom-center
        self._action_deck.adjustSize()
        dw = self._action_deck.width()
        dh = self._action_deck.height()
        deck_y = H - dh - 16
        self._action_deck.move((W - dw) // 2, deck_y)

        # 7. In-HUD Micro-Sparklines
        self._spark_spd.move(max(16, cx - 280), cy + 95)
        self._spark_alt.move(min(W - self._spark_alt.width() - 16, cx + 105), cy + 95)

        att_w = self._spark_att.width()
        att_h = self._spark_att.height()
        self._spark_att.move((W - att_w) // 2, deck_y - att_h - 10)

        # Elevate overlays above camera
        for w in (self._hud, self._radar, self._log_panel,
                  self._spark_spd, self._spark_alt, self._spark_att,
                  self._ctrl_badge, self._stats_card, self._action_deck):
            w.raise_()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._position_overlays)

    # ── Keyboard Event Handlers ───────────────────────────────────────

    def handle_key_down(self, key: int) -> bool:
        handled_keys = {
            Qt.Key.Key_W, Qt.Key.Key_A, Qt.Key.Key_S, Qt.Key.Key_D,
            Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right,
            Qt.Key.Key_T, Qt.Key.Key_L, Qt.Key.Key_Escape, Qt.Key.Key_Space,
            Qt.Key.Key_P, Qt.Key.Key_O,
        }

        if key in handled_keys:
            self._pressed_keys.add(key)
            if key == Qt.Key.Key_T:
                self._on_takeoff_clicked()
            elif key == Qt.Key.Key_L:
                self._on_land_clicked()
            elif key == Qt.Key.Key_Escape:
                self._on_emergency_clicked()
            elif key == Qt.Key.Key_Space:
                self._pressed_keys.clear()
                self._drone.send_rc(0, 0, 0, 0)
            elif key == Qt.Key.Key_P:
                self._toggle_plots()
            elif key == Qt.Key.Key_O:
                self._toggle_ai()
            return True
        return False

    def handle_key_up(self, key: int) -> bool:
        if key in self._pressed_keys:
            self._pressed_keys.discard(key)
            return True
        return False

    # ── Unified RC Loop (25 Hz) ───────────────────────────────────────

    @Slot()
    def _rc_loop_tick(self):
        if not self._drone.is_connected or self._mission.is_running:
            return

        k_lr, k_fb, k_ud, k_yaw = 0, 0, 0, 0
        spd = self._rc_speed

        K = Qt.Key
        if K.Key_A     in self._pressed_keys: k_lr  -= spd
        if K.Key_D     in self._pressed_keys: k_lr  += spd
        if K.Key_W     in self._pressed_keys: k_fb  += spd
        if K.Key_S     in self._pressed_keys: k_fb  -= spd
        if K.Key_Up    in self._pressed_keys: k_ud  += spd
        if K.Key_Down  in self._pressed_keys: k_ud  -= spd
        if K.Key_Left  in self._pressed_keys: k_yaw -= spd
        if K.Key_Right in self._pressed_keys: k_yaw += spd

        g_lr, g_fb, g_ud, g_yaw = self._gamepad_rc

        final_lr  = k_lr  if abs(k_lr)  > abs(g_lr)  else g_lr
        final_fb  = k_fb  if abs(k_fb)  > abs(g_fb)  else g_fb
        final_ud  = k_ud  if abs(k_ud)  > abs(g_ud)  else g_ud
        final_yaw = k_yaw if abs(k_yaw) > abs(g_yaw) else g_yaw

        self._drone.send_rc(final_lr, final_fb, final_ud, final_yaw)

    @Slot(int, int, int, int)
    def _on_gamepad_rc(self, lr: int, fb: int, ud: int, yaw: int):
        self._gamepad_rc = (lr, fb, ud, yaw)

    @Slot(str, bool)
    def _on_gamepad_status(self, name: str, connected: bool):
        if connected:
            self._ctrl_badge.setText(f"🎮 {name.upper()} [ACTIVE]")
            self._ctrl_badge.setStyleSheet(
                "background: rgba(10, 35, 20, 0.9); border: 1px solid #55ff99; "
                "border-radius: 6px; padding: 5px 12px; font-weight: 600; color: #55ff99;"
            )
            self._log(f"Controller attached: {name}", "ok")
        else:
            self._ctrl_badge.setText("🎮 NO GAMEPAD // KEYBOARD PILOT")
            self._ctrl_badge.setStyleSheet(
                "background: rgba(6, 20, 14, 0.82); border: 1px solid rgba(51, 187, 102, 0.55); "
                "border-radius: 6px; padding: 5px 12px; font-weight: 600; color: #55ff99;"
            )
            self._log("Controller disconnected. Keyboard primary.", "warn")
        self._ctrl_badge.adjustSize()
        self._position_overlays()

    # ── Drone Control Slots ───────────────────────────────────────────

    @Slot()
    def _on_connect_clicked(self):
        if self._drone.is_connected:
            self._log("Disengaging uplink...", "warn")
            self._btn_connect.setEnabled(False)
            threading.Thread(target=self._do_disconnect, daemon=True).start()
        else:
            self._log("Establishing tactical uplink...", "ok")
            self._btn_connect.setEnabled(False)
            threading.Thread(target=self._do_connect, daemon=True).start()

    def _do_connect(self):
        ok = self._drone.connect()
        if ok:
            resp = self._drone.stream_on()
            if resp == "ok":
                self._video.start()

    def _do_disconnect(self):
        self._video.stop()
        self._drone.disconnect()

    @Slot()
    def _on_takeoff_clicked(self):
        if not self._drone.is_connected:
            self._log("Link offline. Cannot launch.", "err")
            return
        self._log("Initiating aircraft launch...", "ok")
        self._btn_takeoff.setEnabled(False)
        threading.Thread(target=self._do_takeoff, daemon=True).start()

    def _do_takeoff(self):
        resp = self._drone.takeoff()
        if resp == "ok":
            self._flying = True
            self._set_mode("AIRBORNE")
            self._hud.set_radio_message("AIRBORNE // WEAPONS FREE")
        else:
            self._log(f"Launch aborted: {resp}", "err")
        self._btn_takeoff.setEnabled(True)

    @Slot()
    def _on_land_clicked(self):
        if not self._drone.is_connected:
            return
        self._log("Executing RTB landing sequence...", "ok")
        self._btn_land.setEnabled(False)
        threading.Thread(target=self._do_land, daemon=True).start()

    def _do_land(self):
        resp = self._drone.land()
        self._flying = False
        self._set_mode("GROUNDED")
        self._hud.set_radio_message("TOUCHDOWN CONFIRMED")
        self._btn_land.setEnabled(True)

    @Slot()
    def _on_emergency_clicked(self):
        self._log("⚠ EMERGENCY CUTOFF ACTIVATED", "err")
        self._drone.emergency()
        self._flying = False
        self._set_mode("E-STOP")
        self._hud.set_radio_message("EMERGENCY ENGINE CUT")

    @Slot()
    def _on_drone_connected(self):
        self._log("Tactical uplink established!", "ok")
        bat = self._drone.query_battery()
        self._log(f"Power cell: {bat}%", "ok")
        self._btn_connect.setText("⚡ DISCONNECT")
        self._btn_connect.setEnabled(True)
        self._set_mode("CONNECTED")
        self._hud.set_radio_message("UPLINK SECURED // ALL SENSORS GREEN")

    @Slot()
    def _on_drone_disconnected(self):
        self._log("Tactical uplink severed.", "warn")
        self._flying = False
        self._btn_connect.setText("⚡ UPLINK")
        self._btn_connect.setEnabled(True)
        self._set_mode("STANDBY")
        self._hud.set_radio_message("LINK LOST")
        self._cam.clear_frame()

    @Slot(str)
    def _on_drone_error(self, msg: str):
        self._log(f"Error: {msg}", "err")
        self._btn_connect.setEnabled(True)

    @Slot(DroneState)
    def _on_state_received(self, state: DroneState):
        spd = state.ground_speed_cms

        # 1. Update Fighter HUD
        self._hud.update_telemetry(
            roll=state.roll,
            pitch=state.pitch,
            yaw=state.yaw,
            alt=state.h,
            speed=spd,
            tof=state.tof,
        )

        # 2. Update Tactical Radar
        self._radar.update_pose(
            vx_cms=state.vgx,
            vy_cms=state.vgy,
            yaw_deg=state.yaw,
        )

        # 3. Update In-HUD Micro-Sparklines
        if self._plots_visible:
            self._spark_spd.update_values(
                [spd],
                readouts=[("", f"{spd:.0f} cm/s", QColor(0x55, 0xff, 0x99))]
            )
            self._spark_alt.update_values(
                [state.h],
                readouts=[("", f"{state.h} cm", QColor(0x00, 0xf0, 0xff))]
            )
            # Wrapped Yaw for plotting relative [-180 .. 180]
            yaw_wrapped = (state.yaw + 180) % 360 - 180
            self._spark_att.update_values(
                [state.pitch, state.roll, yaw_wrapped],
                readouts=[
                    ("P", f"{state.pitch:+.0f}°", QColor(0x55, 0xff, 0x99)),
                    ("R", f"{state.roll:+.0f}°",  QColor(0x00, 0xf0, 0xff)),
                    ("Y", f"{int(state.yaw):03d}°", QColor(0xff, 0xbb, 0x33)),
                ]
            )

        # 4. Update Glass Telemetry Pod
        bat_color = "#55ff99" if state.bat > 30 else ("#ffbb33" if state.bat > 15 else "#ff4455")
        self._stats_card.setText(
            f"⚡ BAT: <span style='color:{bat_color};'>{state.bat}%</span> | "
            f"TOF: <span style='color:#55ff99;'>{state.tof}cm</span> | "
            f"TEMP: <span style='color:#55ff99;'>{state.temp_avg:.0f}°C</span>"
        )
        self._stats_card.adjustSize()
        self._stats_card.move(self._cam.width() - self._stats_card.width() - 16, 14)

    @Slot(list)
    def _on_execute_mission(self, waypoints: list):
        if not waypoints:
            self._log("Radar: No waypoints plotted.", "warn")
            return
        if not self._drone.is_connected:
            self._log("Radar: Connect drone before mission launch.", "err")
            return

        self._log(f"Engaging autonomous trajectory ({len(waypoints)} WPs)...", "ok")
        self._hud.set_radio_message(f"AUTONOMOUS MISSION // {len(waypoints)} WAYPOINTS")
        self._mission.start_mission(waypoints, self._radar._drone_x, self._radar._drone_y)

    def _log(self, msg: str, level: str = "ok"):
        self._logger._log(msg, level)

    def _set_mode(self, mode: str):
        def _u():
            self._lbl_mode.setText(f"MODE: {mode}")
        QTimer.singleShot(0, _u)

    def closeEvent(self, event):
        self._rc_timer.stop()
        self._video.stop()
        self._detector.stop()
        if self._drone.is_connected:
            self._drone.disconnect()
        event.accept()
