"""
src/drone/mission.py
Pure-Python mission data model (no Qt): waypoints, helpers and estimates.

Coordinates are in centimetres in a local frame anchored at Home (0, 0):
+X = right/east, +Y = forward/north. There is no GPS on a Tello, so the frame is
dead-reckoned (IMU + vision positioning).
"""

import math
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple

CMDS = ("TAKEOFF", "GO", "ROTATE", "HOVER", "FLIP", "LAND")

DEFAULT_ALT_CM   = 150.0
DEFAULT_SPEED    = 50          # cm/s
AVG_SPEED_CMS    = 50.0        # used for time estimates
FULL_BATTERY_S   = 13 * 60.0   # rough Tello endurance at 100 %


@dataclass
class Waypoint:
    cmd: str = "GO"
    x: float = 0.0          # cm
    y: float = 0.0          # cm
    alt: float = DEFAULT_ALT_CM   # cm above takeoff
    param: str = ""         # GO: speed cm/s | ROTATE: +cw/-ccw deg | HOVER: s | FLIP: f/b/l/r

    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict) -> "Waypoint":
        cmd = str(d.get("cmd", "GO")).upper()
        if cmd not in CMDS:
            cmd = "GO"
        return Waypoint(
            cmd=cmd,
            x=float(d.get("x", 0.0)),
            y=float(d.get("y", 0.0)),
            alt=float(d.get("alt", DEFAULT_ALT_CM)),
            param=str(d.get("param", "")),
        )


def default_param(cmd: str) -> str:
    return {"GO": str(DEFAULT_SPEED), "ROTATE": "90", "HOVER": "3", "FLIP": "f"}.get(cmd, "")


def param_float(wp: Waypoint, fallback: float) -> float:
    try:
        return float(wp.param)
    except (TypeError, ValueError):
        return fallback


def seg_length(a: Waypoint, b: Waypoint) -> float:
    """Horizontal distance between two waypoints (cm)."""
    return math.hypot(b.x - a.x, b.y - a.y)


def bearing_deg(a: Waypoint, b: Waypoint) -> float:
    """Compass bearing a→b (0 = +Y/north, clockwise)."""
    return (math.degrees(math.atan2(b.x - a.x, b.y - a.y)) + 360.0) % 360.0


def cumulative(items: List[Waypoint]) -> Tuple[List[float], float]:
    """Cumulative horizontal path length at every waypoint, plus total (cm)."""
    cum, total = [], 0.0
    for i, w in enumerate(items):
        if i:
            total += seg_length(items[i - 1], w)
        cum.append(total)
    return cum, total


def estimate(items: List[Waypoint]) -> Tuple[float, float, float]:
    """Return (path_length_cm, time_s, battery_percent) — rough planning estimate."""
    _, length = cumulative(items)
    t = 0.0
    for i, w in enumerate(items):
        if w.cmd == "TAKEOFF":
            t += 5.0
        elif w.cmd == "LAND":
            t += 4.0
        elif w.cmd == "ROTATE":
            t += 2.0
        elif w.cmd == "FLIP":
            t += 3.0
        elif w.cmd == "HOVER":
            t += param_float(w, 3.0)
        elif w.cmd == "GO" and i:
            p = items[i - 1]
            spd = max(10.0, param_float(w, DEFAULT_SPEED))
            t += seg_length(p, w) / spd + abs(w.alt - p.alt) / spd + 1.0
    return length, t, t / FULL_BATTERY_S * 100.0


def outside_fence(items: List[Waypoint], radius_cm: float) -> List[int]:
    return [i for i, w in enumerate(items) if math.hypot(w.x, w.y) > radius_cm]
