"""
src/input/gamepad_handler.py
Gamepad & Controller handler for Tello Control Station using pygame.

Supports:
  - Sony PlayStation 4 (DualShock 4) & PS5 (DualSense)
  - Nintendo Switch Pro Controller & Joy-Cons
  - Xbox 360 / Xbox One / Series X / XInput
  - Generic USB Gamepads & Flight Sticks

Mapping (Standard Drone Mode 2):
  - Left Stick Vertical:    Throttle (Up / Down)
  - Left Stick Horizontal:  Yaw (Turn CCW / CW)
  - Right Stick Vertical:   Pitch (Forward / Backward)
  - Right Stick Horizontal: Roll (Left / Right)

Buttons (Standardized across layouts):
  - Action Bottom (Cross / A):    Takeoff
  - Action Right  (Circle / B):   Land
  - Action Top    (Triangle / Y): Flip Forward
  - Action Left   (Square / X):   Hover (zero RC)
  - L1 / LB:                      Emergency Cutoff
  - R1 / RB:                      Speed Boost Toggle
"""

import time
from typing import Optional

import pygame
from PySide6.QtCore import QObject, QTimer, Signal


class GamepadHandler(QObject):
    """
    Polls connected gamepad at 30 Hz and emits RC signals and button events.
    Automatically detects gamepad hotplugging / disconnects.
    """

    rc_changed       = Signal(int, int, int, int)   # (lr, fb, ud, yaw) range -100..100
    takeoff_pressed  = Signal()
    land_pressed     = Signal()
    emergency_pressed= Signal()
    flip_pressed     = Signal(str)                  # 'f', 'b', 'l', 'r'
    status_changed   = Signal(str, bool)            # (controller_name, is_connected)

    DEADZONE = 0.12        # Ignore tiny stick drifts
    POLL_INTERVAL_MS = 33  # ~30 Hz

    def __init__(self, parent=None):
        super().__init__(parent)

        self._initialized = False
        self._joystick: Optional[pygame.joystick.Joystick] = None
        self._controller_name = "None"
        self._speed_boost = False
        self._base_speed = 60
        self._boost_speed = 90

        # State tracking to avoid repeated triggers on held buttons
        self._prev_buttons = {}

        self._init_pygame()

        # Polling timer
        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    def _init_pygame(self):
        try:
            if not pygame.get_init():
                pygame.init()
            if not pygame.joystick.get_init():
                pygame.joystick.init()
            self._initialized = True
            self._check_connection()
        except Exception as e:
            print(f"[Gamepad] Init warning: {e}")

    def _check_connection(self):
        """Check if any joystick is connected."""
        if not self._initialized:
            return

        count = pygame.joystick.get_count()
        if count > 0 and self._joystick is None:
            try:
                self._joystick = pygame.joystick.Joystick(0)
                self._joystick.init()
                self._controller_name = self._joystick.get_name()
                print(f"[Gamepad] Connected: {self._controller_name}")
                self.status_changed.emit(self._controller_name, True)
            except Exception as e:
                print(f"[Gamepad] Connect error: {e}")
                self._joystick = None
        elif count == 0 and self._joystick is not None:
            print("[Gamepad] Disconnected")
            self._joystick = None
            self._controller_name = "None"
            self.status_changed.emit("None", False)

    @property
    def is_connected(self) -> bool:
        return self._joystick is not None

    @property
    def controller_name(self) -> str:
        return self._controller_name

    def _apply_deadzone(self, val: float) -> float:
        """Removes stick center drift and rescales linearly."""
        if abs(val) < self.DEADZONE:
            return 0.0
        sign = 1.0 if val > 0 else -1.0
        return sign * (abs(val) - self.DEADZONE) / (1.0 - self.DEADZONE)

    def _poll(self):
        if not self._initialized:
            return

        # Process pygame event queue (required for joystick updates)
        for event in pygame.event.get():
            if event.type in (pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED):
                self._check_connection()

        if self._joystick is None:
            return

        # Safety verify
        try:
            num_axes = self._joystick.get_numaxes()
            num_buttons = self._joystick.get_numbuttons()
        except Exception:
            self._joystick = None
            return

        # ── Axis Mapping (Standard Drone Mode 2) ─────────────────────
        # Most controllers:
        # Axis 0: Left Stick X  (Yaw)
        # Axis 1: Left Stick Y  (Throttle - inverted, pushing up is negative in raw SDL)
        # Axis 2: Right Stick X (or trigger on some)
        # Axis 3: Right Stick Y
        # Nintendo Switch / PS4 / Xbox standard axes:
        # Left Stick: Axis 0 (X), Axis 1 (Y)
        # Right Stick: Axis 2 or 3 (X), Axis 3 or 4 (Y)

        raw_ls_x = self._joystick.get_axis(0) if num_axes > 0 else 0.0
        raw_ls_y = self._joystick.get_axis(1) if num_axes > 1 else 0.0

        # Right stick usually on axis 2, 3 or 3, 4
        if num_axes >= 5:
            # Typical Xbox/PS4 controller with triggers on 2/5 or 4/5
            # Usually: Axis 2 = Right X (or L-trigger), Axis 3 = Right X/Y, Axis 4 = Right Y
            # SDL standard: Axis 0=LX, 1=LY, 2=RX (or trigger), 3=RY, 4=Trigger
            raw_rs_x = self._joystick.get_axis(2) if num_axes > 2 else 0.0
            raw_rs_y = self._joystick.get_axis(3) if num_axes > 3 else 0.0
            # If axis 2 is a trigger (idle at -1.0), use axis 3 & 4
            if abs(raw_rs_x + 1.0) < 0.05 and num_axes >= 5:
                raw_rs_x = self._joystick.get_axis(3)
                raw_rs_y = self._joystick.get_axis(4)
        elif num_axes >= 4:
            raw_rs_x = self._joystick.get_axis(2)
            raw_rs_y = self._joystick.get_axis(3)
        else:
            raw_rs_x = 0.0
            raw_rs_y = 0.0

        # Apply deadzone
        ls_x = self._apply_deadzone(raw_ls_x)
        ls_y = self._apply_deadzone(raw_ls_y)
        rs_x = self._apply_deadzone(raw_rs_x)
        rs_y = self._apply_deadzone(raw_rs_y)

        # Scale by speed limit
        max_spd = self._boost_speed if self._speed_boost else self._base_speed

        # RC values:
        # ud: up/down (pushing up gives negative Y in SDL -> invert to positive)
        # yaw: left/right
        # fb: forward/backward (pushing up gives negative Y in SDL -> invert to positive)
        # lr: left/right (positive = right)
        ud  = int(-ls_y * max_spd)
        yaw = int(ls_x * max_spd)
        fb  = int(-rs_y * max_spd)
        lr  = int(rs_x * max_spd)

        self.rc_changed.emit(lr, fb, ud, yaw)

        # ── Buttons ──────────────────────────────────────────────────
        # Button 0 (Cross / A): Takeoff
        # Button 1 (Circle / B): Land
        # Button 2 (Square / X): Hover
        # Button 3 (Triangle / Y): Flip Forward
        # Button 4 (L1 / LB): Emergency
        # Button 5 (R1 / RB): Boost Toggle

        for btn_idx in range(min(num_buttons, 14)):
            pressed = self._joystick.get_button(btn_idx)
            was_pressed = self._prev_buttons.get(btn_idx, False)

            # Fire only on initial press (edge trigger)
            if pressed and not was_pressed:
                if btn_idx == 0:    # Cross / A
                    self.takeoff_pressed.emit()
                elif btn_idx == 1:  # Circle / B
                    self.land_pressed.emit()
                elif btn_idx == 3:  # Triangle / Y
                    self.flip_pressed.emit('f')
                elif btn_idx == 4:  # L1 / LB
                    self.emergency_pressed.emit()
                elif btn_idx == 5:  # R1 / RB
                    self._speed_boost = not self._speed_boost

            self._prev_buttons[btn_idx] = pressed
