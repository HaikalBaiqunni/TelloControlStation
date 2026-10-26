"""
src/drone/pose.py
Dead-reckoned local position of the drone (no GPS on a Tello).

Integrates the ground velocity reported in the state stream. The frame is anchored at
Home (0, 0) in centimetres: +X right/east, +Y forward/north.
"""

import math
import time
from typing import List, Tuple


class PoseTracker:
    TRAIL_MAX = 200

    def __init__(self):
        self._last = time.time()
        self.reset()

    def reset(self):
        self.x = 0.0           # cm
        self.y = 0.0           # cm
        self.yaw = 0.0         # deg
        self.alt = 0.0         # cm
        self.trail: List[Tuple[float, float]] = [(0.0, 0.0)]

    def update(self, vx_cms: float, vy_cms: float, yaw_deg: float, alt_cm: float = 0.0):
        now = time.time()
        dt = min(now - self._last, 0.2)
        self._last = now

        self.yaw = yaw_deg
        self.alt = alt_cm
        rad = math.radians(yaw_deg)
        self.x += (vx_cms * math.sin(rad) + vy_cms * math.cos(rad)) * dt
        self.y += (vx_cms * math.cos(rad) - vy_cms * math.sin(rad)) * dt

        lx, ly = self.trail[-1]
        if (self.x - lx) ** 2 + (self.y - ly) ** 2 > 25:
            self.trail.append((self.x, self.y))
            if len(self.trail) > self.TRAIL_MAX:
                self.trail.pop(0)
