"""
src/drone/mission_planner.py
Waypoint mission execution thread for Tello SDK 1.3.

Takes a sequence of 2D/3D waypoints (relative to Home in cm),
calculates the delta steps (dx, dy), and safely commands the Tello.
"""

import math
import threading
import time
from typing import List, Tuple, Optional

from PySide6.QtCore import QObject, Signal


class MissionPlanner(QObject):
    """
    Executes a sequence of waypoints step-by-step.
    Emits signals on progress, waypoint reached, and completion.
    """

    mission_started  = Signal(int)           # total waypoints
    waypoint_reached = Signal(int, float, float)  # (index, x_cm, y_cm)
    mission_finished = Signal(bool, str)     # (success, message)

    def __init__(self, tello_sdk, logger, parent=None):
        super().__init__(parent)
        self._sdk = tello_sdk
        self._logger = logger
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._abort = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start_mission(self, waypoints: List[Tuple[float, float]], current_x: float = 0.0, current_y: float = 0.0):
        """Start executing waypoints in a background worker thread."""
        if not waypoints:
            self.mission_finished.emit(False, "No waypoints specified.")
            return

        if not self._sdk.is_connected:
            self.mission_finished.emit(False, "Drone not connected.")
            return

        if self._running:
            self._logger.warning("Mission already in progress.")
            return

        self._running = True
        self._abort = False
        self._thread = threading.Thread(
            target=self._run_mission_worker,
            args=(waypoints, current_x, current_y),
            daemon=True,
            name="tello-mission"
        )
        self._thread.start()

    def abort_mission(self):
        """Abort the current mission immediately."""
        self._abort = True
        self._running = False
        self._logger.warning("Mission aborted by user.")

    def _run_mission_worker(self, waypoints: List[Tuple[float, float]], start_x: float, start_y: float):
        self.mission_started.emit(len(waypoints))
        self._logger.info(f"Starting mission with {len(waypoints)} waypoints...")

        curr_x = start_x
        curr_y = start_y

        for idx, (target_x, target_y) in enumerate(waypoints):
            if self._abort or not self._running:
                break

            # Calculate relative move in world frame (cm)
            # World frame: +Y is Forward/North, +X is Right/East
            dx = target_x - curr_x
            dy = target_y - curr_y
            dist = math.hypot(dx, dy)

            if dist < 20:
                # Tello minimum step is 20 cm
                curr_x = target_x
                curr_y = target_y
                self.waypoint_reached.emit(idx + 1, target_x, target_y)
                continue

            # Command move using discrete forward/back/left/right
            # (more reliable on non-EDU firmware than go x y z)
            self._logger.info(f"Navigating to WP{idx + 1}: ({target_x:.0f}, {target_y:.0f}) cm, dist={dist:.0f}cm")

            # 1. Forward / Back component
            if abs(dy) >= 20:
                step_y = max(20, min(500, int(abs(dy))))
                cmd_y = f"forward {step_y}" if dy > 0 else f"back {step_y}"
                resp = self._sdk.send_command(cmd_y, timeout=12.0)
                if resp != "ok" and not self._abort:
                    self._logger.warning(f"WP step warning: {cmd_y} -> {resp}")
                time.sleep(0.5)

            if self._abort:
                break

            # 2. Right / Left component
            if abs(dx) >= 20:
                step_x = max(20, min(500, int(abs(dx))))
                cmd_x = f"right {step_x}" if dx > 0 else f"left {step_x}"
                resp = self._sdk.send_command(cmd_x, timeout=12.0)
                if resp != "ok" and not self._abort:
                    self._logger.warning(f"WP step warning: {cmd_x} -> {resp}")
                time.sleep(0.5)

            curr_x = target_x
            curr_y = target_y
            self.waypoint_reached.emit(idx + 1, target_x, target_y)

        self._running = False
        if not self._abort:
            self._logger.info("Mission completed successfully!")
            self.mission_finished.emit(True, "All waypoints reached.")
        else:
            self.mission_finished.emit(False, "Mission aborted.")
