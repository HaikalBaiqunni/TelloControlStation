"""
src/ui/main_window.py
Tello Control Station — glass cockpit with fighter HUD, AI vision and waypoint mission control.

Pages (tabs in the top bar):
  FLIGHT DATA  - full-bleed FPV + fighter HUD + live mission map / progress strip + action deck
  FLIGHT PLAN  - waypoint planner (map, table, altitude profile, patterns)
  LOGS         - flight log

Input: keyboard + gamepad with a global focus lock (keys are not stolen while typing in a field).
"""

import math
import threading
from typing import Optional

import numpy as np

from PySide6.QtCore import Qt, QTimer, Signal, Slot, QObject, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractSpinBox, QApplication, QComboBox, QLineEdit, QMainWindow,
    QStackedWidget,
)

from src.drone.mission import Waypoint, estimate, outside_fence
from src.drone.mission_planner import MissionPlanner
from src.drone.object_detector import ObjectDetector
from src.drone.pose import PoseTracker
from src.drone.state_parser import DroneState
from src.drone.tello_sdk import TelloSDK
from src.drone.video_stream import VideoStreamThread
from src.input.gamepad_handler import GamepadHandler
from src.ui import theme
from src.ui.mission_model import MissionModel
from src.ui.pages import FlyPage, LogsPage, PlanPage
from src.ui.widgets.mission_widgets import mmss
from src.utils.logger import FlightLogger


# ══════════════════════════════════════════════════════════════════════
#  Global Keyboard Control Filter
# ══════════════════════════════════════════════════════════════════════

# Widgets that must keep their own keystrokes (typing, row navigation, combo boxes)
_TEXT_WIDGETS = (QLineEdit, QAbstractSpinBox, QAbstractItemView, QComboBox)


class GlobalControlFilter(QObject):
    def __init__(self, main_window):
        super().__init__(main_window)
        self._mw = main_window

    def eventFilter(self, watched, event):
        t = event.type()
        if t in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if isinstance(QApplication.focusWidget(), _TEXT_WIDGETS):
                return False
            ev: QKeyEvent = event
            if not ev.isAutoRepeat():
                handled = (self._mw.handle_key_down(ev.key()) if t == QEvent.Type.KeyPress
                           else self._mw.handle_key_up(ev.key()))
                if handled:
                    return True
        return super().eventFilter(watched, event)


# ══════════════════════════════════════════════════════════════════════
#  Main Window
# ══════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    ui_call = Signal(object)          # run a callable in the GUI thread (from worker threads)
    log_sig = Signal(str, str, str)   # ts, msg, level

    FLY, PLAN, LOGS = 0, 1, 2

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tello Control Station // Glass Cockpit & Mission Control")
        self.setMinimumSize(1180, 700)
        self.resize(1366, 768)
        self.setStyleSheet(theme.APP_STYLE)

        # ── Core Subsystems ─────────────────────────────────────────
        self._drone    = TelloSDK(self)
        self._video    = VideoStreamThread(self)
        self._logger   = FlightLogger(max_entries=300)
        self._gamepad  = GamepadHandler(self)
        self._mission  = MissionPlanner(self._drone, self._logger, self)
        self._detector = ObjectDetector(model_path="yolov8n.pt", parent=self)
        self._pose     = PoseTracker()
        self._model    = MissionModel(self)

        self._flying = False
        self._last_state: Optional[DroneState] = None
        self._pressed_keys: set = set()
        self._rc_speed = 60
        self._gamepad_rc = (0, 0, 0, 0)
        self._plots_visible = True
        self._ai_enabled    = True

        self._build_ui()
        self._connect_signals()

        self._key_filter = GlobalControlFilter(self)
        QApplication.instance().installEventFilter(self._key_filter)

        # RC control loop (25 Hz)
        self._rc_timer = QTimer(self)
        self._rc_timer.setInterval(40)
        self._rc_timer.timeout.connect(self._rc_loop_tick)
        self._rc_timer.start()

        # Mission HUD / chips refresh (5 Hz)
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(200)
        self._ui_timer.timeout.connect(self._ui_tick)
        self._ui_timer.start()

        self._log("AVIONICS GLASS & AI VISION ONLINE", "ok")
        self._log("Ready for sortie. Establish drone link.", "ok")

    # ── UI ───────────────────────────────────────────────────────────

    def _build_ui(self):
        self._fly  = FlyPage(self._model, self._pose)
        self._plan = PlanPage(self._model, self._pose)
        self._logs = LogsPage()
        self._pages = [self._fly, self._plan, self._logs]
        self._topbars = [p.topbar for p in self._pages]

        self._stack = QStackedWidget()
        for p in self._pages:
            self._stack.addWidget(p)
        self.setCentralWidget(self._stack)

        # aliases kept for scripts/gen_screenshots.py
        self._cam = self._fly
        self._hud = self._fly.hud

        self._set_mode("STANDBY")
        self._set_pad("KEYBOARD PILOT", False)
        for tb in self._topbars:
            tb.set_link(False)

    def _connect_signals(self):
        f = self._fly
        for tb in self._topbars:
            tb.tab_changed.connect(self._goto)
        f.btn_edit.clicked.connect(lambda: self._goto(self.PLAN))

        # Deck buttons
        f.btn_connect.clicked.connect(self._on_connect_clicked)
        f.btn_takeoff.clicked.connect(self._on_takeoff_clicked)
        f.btn_land.clicked.connect(self._on_land_clicked)
        f.btn_emergency.clicked.connect(self._on_emergency_clicked)
        f.btn_rst_pos.clicked.connect(self._reset_home)
        f.btn_plot.clicked.connect(self._toggle_plots)
        f.btn_ai.clicked.connect(self._toggle_ai)
        f.btn_start.clicked.connect(self._start_mission)
        self._plan.start_requested.connect(self._start_mission)
        f.btn_abort.clicked.connect(self._mission.abort_mission)
        f.btn_skip.clicked.connect(self._mission.skip_current)

        # Thread bridges
        self.ui_call.connect(self._run_ui)
        self.log_sig.connect(self._on_log)
        self._logger.add_callback(lambda ts, msg, lvl: self.log_sig.emit(ts, msg, lvl))

        # Drone SDK
        self._drone.connected_sig.connect(self._on_drone_connected)
        self._drone.disconnected_sig.connect(self._on_drone_disconnected)
        self._drone.error_sig.connect(self._on_drone_error)
        self._drone.state_received.connect(self._on_state_received)

        # Video
        self._video.frame_ready.connect(self._on_video_frame)
        self._video.stream_error.connect(lambda e: self._log(f"Video: {e}", "err"))
        self._video.stream_started.connect(lambda: self._log("Optical sensor link engaged", "ok"))
        self._video.stream_stopped.connect(f.clear_frame)

        # AI detector
        self._detector.detections_ready.connect(f.set_detections)
        self._detector.model_loaded.connect(self._on_detector_loaded)

        # Gamepad
        self._gamepad.rc_changed.connect(self._on_gamepad_rc)
        self._gamepad.takeoff_pressed.connect(self._on_takeoff_clicked)
        self._gamepad.land_pressed.connect(self._on_land_clicked)
        self._gamepad.emergency_pressed.connect(self._on_emergency_clicked)
        self._gamepad.flip_pressed.connect(
            lambda d: threading.Thread(target=lambda: self._drone.flip(d), daemon=True).start())
        self._gamepad.status_changed.connect(self._on_gamepad_status)

        # Mission
        self._mission.item_started.connect(self._on_item_started)
        self._mission.waypoint_reached.connect(self._on_wp_reached)
        self._mission.mission_finished.connect(self._on_mission_finished)
        self._model.changed.connect(self._on_plan_edited)

    # ── Thread-safe helpers ──────────────────────────────────────────

    @Slot(object)
    def _run_ui(self, fn):
        fn()

    def _in_ui(self, fn):
        """Call from any thread: runs `fn` in the GUI thread."""
        self.ui_call.emit(fn)

    @Slot(str, str, str)
    def _on_log(self, ts: str, msg: str, level: str):
        self._logs.log.add_entry(ts, msg, level)

    def _log(self, msg: str, level: str = "ok"):
        self._logger._log(msg, level)

    def _set_mode(self, mode: str):
        self._in_ui(lambda: [tb.set_mode(mode) for tb in self._topbars])

    def _set_pad(self, text: str, active: bool):
        for tb in self._topbars:
            tb.set_pad(text, active)

    def _hud_msg(self, msg: str):
        self._in_ui(lambda: self._hud.set_radio_message(msg))

    def _goto(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for tb in self._topbars:
            tb.set_tab(idx)

    # ── Toggles ──────────────────────────────────────────────────────

    def _on_video_frame(self, frame: np.ndarray):
        self._fly.set_frame(frame)
        if self._ai_enabled:
            self._detector.push_frame(frame)

    @Slot(bool)
    def _on_detector_loaded(self, ok: bool):
        self._log("AI YOLOv8 Vision Engine ready" if ok else "AI Engine failed", "ok" if ok else "err")

    def _toggle_plots(self):
        self._plots_visible = not self._plots_visible
        self._fly.fdata.setVisible(self._plots_visible)
        self._fly.btn_plot.setText(f"📈 DATA: {'ON' if self._plots_visible else 'OFF'}")

    def _toggle_ai(self):
        self._ai_enabled = not self._ai_enabled
        self._detector.set_enabled(self._ai_enabled)
        self._fly.set_ai_enabled(self._ai_enabled)
        self._fly.btn_ai.setText(f"🎯 AI TRACK: {'ON' if self._ai_enabled else 'OFF'}")
        self._log(f"AI Target Recognition: {'ENABLED' if self._ai_enabled else 'DISABLED'}",
                  "ok" if self._ai_enabled else "warn")

    def _reset_home(self):
        self._pose.reset()
        self._log("Home reset: local frame re-anchored at current position", "ok")

    # ── Keyboard ─────────────────────────────────────────────────────

    def handle_key_down(self, key: int) -> bool:
        K = Qt.Key
        handled = {K.Key_W, K.Key_A, K.Key_S, K.Key_D, K.Key_Up, K.Key_Down, K.Key_Left, K.Key_Right,
                   K.Key_T, K.Key_L, K.Key_Escape, K.Key_Space, K.Key_P, K.Key_O, K.Key_M}
        if key not in handled:
            return False
        self._pressed_keys.add(key)
        if key == K.Key_T:
            self._on_takeoff_clicked()
        elif key == K.Key_L:
            self._on_land_clicked()
        elif key == K.Key_Escape:
            self._on_emergency_clicked()
        elif key == K.Key_Space:
            self._pressed_keys.clear()
            self._drone.send_rc(0, 0, 0, 0)
        elif key == K.Key_P:
            self._toggle_plots()
        elif key == K.Key_O:
            self._toggle_ai()
        elif key == K.Key_M:
            cur = self._stack.currentIndex()
            self._goto(self.PLAN if cur == self.FLY else self.FLY)
        return True

    def handle_key_up(self, key: int) -> bool:
        if key in self._pressed_keys:
            self._pressed_keys.discard(key)
            return True
        return False

    # ── RC loop ──────────────────────────────────────────────────────

    @Slot()
    def _rc_loop_tick(self):
        k_lr = k_fb = k_ud = k_yaw = 0
        spd = self._rc_speed
        K = Qt.Key
        pk = self._pressed_keys
        if K.Key_A in pk:     k_lr  -= spd
        if K.Key_D in pk:     k_lr  += spd
        if K.Key_W in pk:     k_fb  += spd
        if K.Key_S in pk:     k_fb  -= spd
        if K.Key_Up in pk:    k_ud  += spd
        if K.Key_Down in pk:  k_ud  -= spd
        if K.Key_Left in pk:  k_yaw -= spd
        if K.Key_Right in pk: k_yaw += spd

        g_lr, g_fb, g_ud, g_yaw = self._gamepad_rc
        lr  = k_lr  if abs(k_lr)  > abs(g_lr)  else g_lr
        fb  = k_fb  if abs(k_fb)  > abs(g_fb)  else g_fb
        ud  = k_ud  if abs(k_ud)  > abs(g_ud)  else g_ud
        yaw = k_yaw if abs(k_yaw) > abs(g_yaw) else g_yaw

        self._fly.set_sticks(lr, fb, ud, yaw)
        if not self._drone.is_connected or self._mission.is_running:
            return
        self._drone.send_rc(lr, fb, ud, yaw)

    @Slot(int, int, int, int)
    def _on_gamepad_rc(self, lr: int, fb: int, ud: int, yaw: int):
        self._gamepad_rc = (lr, fb, ud, yaw)

    @Slot(str, bool)
    def _on_gamepad_status(self, name: str, connected: bool):
        if connected:
            self._set_pad(f"🎮 {name.upper()}", True)
            self._log(f"Controller attached: {name}", "ok")
        else:
            self._set_pad("KEYBOARD PILOT", False)
            self._log("Controller disconnected. Keyboard primary.", "warn")

    # ── Drone control ────────────────────────────────────────────────

    @Slot()
    def _on_connect_clicked(self):
        self._fly.btn_connect.setEnabled(False)
        if self._drone.is_connected:
            self._log("Disengaging uplink...", "warn")
            threading.Thread(target=self._do_disconnect, daemon=True).start()
        else:
            self._log("Establishing tactical uplink...", "ok")
            threading.Thread(target=self._do_connect, daemon=True).start()

    def _do_connect(self):
        if self._drone.connect():
            if self._drone.stream_on() == "ok":
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
        self._fly.btn_takeoff.setEnabled(False)
        threading.Thread(target=self._do_takeoff, daemon=True).start()

    def _do_takeoff(self):
        resp = self._drone.takeoff()
        if resp == "ok":
            self._flying = True
            self._set_mode("AIRBORNE")
            self._hud_msg("AIRBORNE // ALL SYSTEMS GREEN")
        else:
            self._log(f"Launch aborted: {resp}", "err")
        self._in_ui(lambda: self._fly.btn_takeoff.setEnabled(True))

    @Slot()
    def _on_land_clicked(self):
        if not self._drone.is_connected:
            return
        self._log("Executing RTB landing sequence...", "ok")
        self._fly.btn_land.setEnabled(False)
        threading.Thread(target=self._do_land, daemon=True).start()

    def _do_land(self):
        self._drone.land()
        self._flying = False
        self._set_mode("GROUNDED")
        self._hud_msg("TOUCHDOWN CONFIRMED")
        self._in_ui(lambda: self._fly.btn_land.setEnabled(True))

    @Slot()
    def _on_emergency_clicked(self):
        self._log("⚠ EMERGENCY CUTOFF ACTIVATED", "err")
        self._mission.abort_mission()
        self._drone.emergency()
        self._flying = False
        if self._model.state == MissionModel.RUNNING:
            self._model.set_state(MissionModel.IDLE)
        self._set_mode("E-STOP")
        self._hud_msg("EMERGENCY ENGINE CUT")

    @Slot()
    def _on_drone_connected(self):
        self._log("Tactical uplink established!", "ok")
        bat = self._drone.query_battery()
        self._log(f"Power cell: {bat}%", "ok")
        self._fly.btn_connect.setText("⚡ DISCONNECT")
        self._fly.btn_connect.setEnabled(True)
        for tb in self._topbars:
            tb.set_link(True)
        self._set_mode("CONNECTED")
        self._hud_msg("UPLINK SECURED // ALL SENSORS GREEN")

    @Slot()
    def _on_drone_disconnected(self):
        self._log("Tactical uplink severed.", "warn")
        self._flying = False
        self._fly.btn_connect.setText("⚡ UPLINK")
        self._fly.btn_connect.setEnabled(True)
        for tb in self._topbars:
            tb.set_link(False)
        self._set_mode("STANDBY")
        self._hud_msg("LINK LOST")
        self._fly.clear_frame()
        self._fly.vehicle.clear_state()

    @Slot(str)
    def _on_drone_error(self, msg: str):
        self._log(f"Error: {msg}", "err")
        self._fly.btn_connect.setEnabled(True)

    @Slot(DroneState)
    def _on_state_received(self, s: DroneState):
        self._last_state = s
        spd = s.ground_speed_cms
        self._pose.update(s.vgx, s.vgy, s.yaw, s.h)

        self._hud.update_telemetry(roll=s.roll, pitch=s.pitch, yaw=s.yaw, alt=s.h, speed=spd,
                                   tof=s.tof, bat=s.bat)
        self._fly.vehicle.update_state(s)

        if self._plots_visible:
            self._fly.trace.update_values(
                [spd, s.h, s.pitch],
                readouts=[("SPD", f"{spd:.0f}", theme.ACCENT), ("ALT", f"{s.h}", theme.WARN),
                          ("P", f"{s.pitch:+.0f}°", theme.OK)])

        caution = ""
        if 0 < s.bat <= 15:
            caution = "LOW BATTERY"
        elif math.hypot(self._pose.x, self._pose.y) > self._model.geofence_cm:
            caution = "GEOFENCE BREACH"
        self._hud.set_caution(caution)

    # ── Mission ──────────────────────────────────────────────────────

    @Slot()
    def _start_mission(self):
        items = self._model.items
        if self._mission.is_running:
            self._log("Mission already in progress.", "warn")
            return
        if not self._drone.is_connected:
            self._log("Connect the drone before starting a mission.", "err")
            return
        if len(items) < 3:
            self._log("Mission is empty - add waypoints in FLIGHT PLAN.", "warn")
            self._goto(self.PLAN)
            return
        bad = outside_fence(items, self._model.geofence_cm)
        if bad:
            self._log(f"Waypoint(s) {bad} outside the {self._model.geofence_cm / 100:.0f} m geofence.", "err")
            self._goto(self.PLAN)
            return

        s = self._last_state
        start_alt = float(s.h) if s and s.h > 10 else 0.0
        start_yaw = float(s.yaw) if s else 0.0
        self._model.set_state(MissionModel.RUNNING)
        self._model.set_target(0)
        self._goto(self.FLY)
        self._log(f"Engaging autonomous mission ({len(items) - 1} items)...", "ok")
        self._hud.set_radio_message(f"AUTONOMOUS MISSION // {len(items) - 1} WAYPOINTS")
        self._set_mode("AUTO MISSION")
        self._mission.start_mission(items, self._pose.x, self._pose.y, start_alt, start_yaw)

    @Slot(int)
    def _on_item_started(self, idx: int):
        self._model.set_target(idx)
        w = self._model.items[idx] if idx < len(self._model.items) else None
        if w:
            self._log(f"WP{idx}: {w.cmd}", "ok")

    @Slot(int, float, float)
    def _on_wp_reached(self, idx: int, x: float, y: float):
        self._log(f"WP{idx} reached: ({x:.0f}, {y:.0f}) cm", "ok")

    @Slot(bool, str)
    def _on_mission_finished(self, ok: bool, msg: str):
        self._model.set_state(MissionModel.DONE if ok else MissionModel.IDLE)
        self._log(f"Mission: {msg}", "ok" if ok else "warn")
        airborne = bool(self._last_state and self._last_state.is_airborne)
        self._flying = airborne
        self._set_mode("AIRBORNE" if airborne else "GROUNDED")
        self._hud.set_radio_message("MISSION COMPLETE" if ok else "MISSION ENDED")

    @Slot()
    def _on_plan_edited(self):
        if self._model.state == MissionModel.DONE:
            self._model.set_state(MissionModel.IDLE)

    @Slot()
    def _ui_tick(self):
        m, pose = self._model, self._pose
        running = m.state == MissionModel.RUNNING
        n = len(m.items) - 1

        if running:
            t = max(1, min(m.target, n))
            tgt = m.items[t]
            dist = math.hypot(tgt.x - pose.x, tgt.y - pose.y)
            _, secs, _ = estimate([Waypoint("GO", pose.x, pose.y, pose.alt)] + m.items[t:])
            hud = f"WP {t}/{n}  DIST {dist / 100:.1f} M  ETA {mmss(secs)}"
            sub = f"WP {t}/{n} · {dist / 100:.1f} m · ETA {mmss(secs)}"
            chip = f"MISSION WP {t}/{n}"
        elif m.state == MissionModel.DONE:
            hud, sub, chip = "MISSION COMPLETE", "COMPLETE", "MISSION DONE"
        elif n >= 2:
            _, secs, _ = estimate(m.items)
            hud = f"MISSION READY  {n - 1} WP  EST {mmss(secs)}"
            sub, chip = f"READY · {n - 1} WP", "MISSION READY"
        else:
            hud, sub, chip = "", "NO MISSION", "MISSION IDLE"

        self._hud.set_mission_info(hud)
        self._fly.live.set_subtitle(sub)
        for tb in self._topbars:
            tb.set_mission(chip, running)

        f = self._fly
        f.btn_start.setEnabled(not running)
        f.btn_abort.setEnabled(running)
        f.btn_skip.setEnabled(running)
        self._plan.btn_start.setEnabled(not running)

    # ── Window ───────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._rc_timer.stop()
        self._ui_timer.stop()
        self._mission.abort_mission()
        self._video.stop()
        self._detector.stop()
        if self._drone.is_connected:
            self._drone.disconnect()
        event.accept()
