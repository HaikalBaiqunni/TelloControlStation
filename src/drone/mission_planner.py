"""
src/drone/mission_planner.py
Autonomous mission execution thread for Tello SDK 1.3 (non-EDU compatible).

Runs a list of mission items (see src/drone/mission.py) one by one:
TAKEOFF, GO (x/y/alt), ROTATE, HOVER, FLIP, LAND. Horizontal moves are decomposed into
`forward/back/left/right` steps (more reliable on non-EDU firmware than `go x y z`),
converted to the drone's body frame using the current heading.
"""

import math
import threading
import time
from typing import List, Optional

from PySide6.QtCore import QObject, Signal

from src.drone.mission import Waypoint, param_float, DEFAULT_SPEED

MIN_STEP = 20     # Tello minimum move (cm)
MAX_STEP = 500    # Tello maximum move (cm)


class MissionPlanner(QObject):
    """Executes mission items step by step and reports progress via signals."""

    mission_started  = Signal(int)                # total items
    item_started     = Signal(int)                # index now being flown to
    waypoint_reached = Signal(int, float, float)  # (index, x_cm, y_cm)
    mission_finished = Signal(bool, str)          # (success, message)

    def __init__(self, tello_sdk, logger, parent=None):
        super().__init__(parent)
        self._sdk = tello_sdk
        self._logger = logger
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._abort = False
        self._skip = False

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Control ──────────────────────────────────────────────────────────

    def start_mission(self, items: List[Waypoint], start_x: float = 0.0, start_y: float = 0.0,
                      start_alt: float = 0.0, start_yaw: float = 0.0):
        if not items:
            self.mission_finished.emit(False, "No mission items.")
            return
        if not self._sdk.is_connected:
            self.mission_finished.emit(False, "Drone not connected.")
            return
        if self._running:
            self._logger.warning("Mission already in progress.")
            return

        self._running = True
        self._abort = False
        self._skip = False
        self._thread = threading.Thread(
            target=self._worker,
            args=([Waypoint(**w.to_dict()) for w in items], start_x, start_y, start_alt, start_yaw),
            daemon=True,
            name="tello-mission",
        )
        self._thread.start()

    def abort_mission(self):
        if self._running:
            self._abort = True
            self._logger.warning("Mission abort requested (current command finishes first).")

    def skip_current(self):
        """Skip the remaining steps of the current item (takes effect between commands)."""
        if self._running:
            self._skip = True
            self._logger.warning("Skipping current waypoint...")

    # ── Worker ───────────────────────────────────────────────────────────

    def _worker(self, items, x, y, alt, yaw):
        self._x, self._y, self._alt, self._hdg = x, y, alt, yaw
        self._speed_set: Optional[int] = None
        self.mission_started.emit(len(items))
        self._logger.info(f"Mission started: {len(items)} items")
        ok, msg = True, "Mission complete."

        try:
            for idx, w in enumerate(items):
                if self._abort:
                    break
                self._skip = False
                self.item_started.emit(idx)
                if not self._exec(w):
                    ok, msg = False, f"Item {idx} ({w.cmd}) failed - mission stopped."
                    break
                self.waypoint_reached.emit(idx, self._x, self._y)
            if self._abort:
                ok, msg = False, "Mission aborted."
        except Exception as e:  # keep the thread from dying silently
            ok, msg = False, f"Mission error: {e}"
            self._logger.error(msg)
        finally:
            self._running = False
        self.mission_finished.emit(ok, msg)

    def _stop(self) -> bool:
        return self._abort or self._skip

    def _cmd(self, cmd: str) -> bool:
        resp = self._sdk.send_command(cmd, timeout=15.0)
        if resp != "ok":
            self._logger.warning(f"{cmd} -> {resp}")
        time.sleep(0.5)
        return resp == "ok"

    def _exec(self, w: Waypoint) -> bool:
        c = w.cmd
        if c == "TAKEOFF":
            if self._alt < MIN_STEP:
                if self._sdk.takeoff() != "ok":
                    self._logger.error("Takeoff failed")
                    return False
                self._alt = 80.0
                time.sleep(1.0)
            self._move_alt(w.alt)
        elif c == "GO":
            spd = int(max(10, min(100, param_float(w, DEFAULT_SPEED))))
            if spd != self._speed_set:
                self._sdk.set_speed(spd)
                self._speed_set = spd
            self._logger.info(f"-> ({w.x:.0f}, {w.y:.0f}) cm @ {w.alt:.0f} cm")
            self._move_alt(w.alt)
            self._move_xy(w.x, w.y)
        elif c == "ROTATE":
            deg = param_float(w, 90.0)
            n = int(min(360, abs(deg)))
            if n >= 1:
                self._cmd(f"{'cw' if deg > 0 else 'ccw'} {n}")
                self._hdg += math.copysign(n, deg)
        elif c == "HOVER":
            end = time.time() + max(0.0, param_float(w, 3.0))
            while time.time() < end and not self._stop():
                time.sleep(0.1)
        elif c == "FLIP":
            d = w.param.strip().lower()[:1]
            self._sdk.flip(d if d in ("f", "b", "l", "r") else "f")
            time.sleep(1.5)
        elif c == "LAND":
            self._move_xy(w.x, w.y)
            if self._sdk.land() != "ok":
                self._logger.warning("Land command not acknowledged")
            self._alt = 0.0
        return True

    def _move_alt(self, target: float):
        d = target - self._alt
        while abs(d) >= MIN_STEP and not self._stop():
            step = int(min(MAX_STEP, abs(d)))
            if not self._cmd(f"{'up' if d > 0 else 'down'} {step}"):
                break
            self._alt += math.copysign(step, d)
            d = target - self._alt

    def _move_xy(self, tx: float, ty: float):
        dx, dy = tx - self._x, ty - self._y
        if math.hypot(dx, dy) < MIN_STEP:
            self._x, self._y = tx, ty
            return
        h = math.radians(self._hdg)
        fwd = dy * math.cos(h) + dx * math.sin(h)
        right = dx * math.cos(h) - dy * math.sin(h)
        for axis, name_pos, name_neg in ((fwd, "forward", "back"), (right, "right", "left")):
            left = abs(axis)
            while left >= MIN_STEP and not self._stop():
                step = int(min(MAX_STEP, left))
                if not self._cmd(f"{name_pos if axis > 0 else name_neg} {step}"):
                    break
                left -= step
        self._x, self._y = tx, ty
