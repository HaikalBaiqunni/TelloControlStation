"""
src/drone/state_parser.py
Parse Tello SDK 1.3 state string received on UDP port 8890.

State string format (semicolon-separated key:value pairs):
  pitch:-1;roll:0;yaw:2;vgx:0;vgy:0;vgz:0;templ:68;temph:70;
  tof:6553;h:0;bat:88;baro:-44.45;agx:-14.00;agy:-5.00;agz:-998.00;
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DroneState:
    """Structured representation of a single Tello telemetry frame."""

    # Attitude (degrees)
    pitch: float = 0.0
    roll: float = 0.0
    yaw: float = 0.0

    # Velocity (cm/s)
    vgx: float = 0.0
    vgy: float = 0.0
    vgz: float = 0.0

    # Temperature (°C)
    templ: int = 0   # lower bound
    temph: int = 0   # upper bound

    # Distance / altitude
    tof: int = 0     # Time-of-flight sensor (cm)
    h: int = 0       # Height above takeoff (cm)
    baro: float = 0.0  # Barometer (cm)

    # Battery (%)
    bat: int = 0

    # Acceleration (mg)
    agx: float = 0.0
    agy: float = 0.0
    agz: float = 0.0

    # Derived / convenience
    @property
    def ground_speed_cms(self) -> float:
        """Horizontal ground speed in cm/s."""
        return (self.vgx ** 2 + self.vgy ** 2) ** 0.5

    @property
    def temp_avg(self) -> float:
        return (self.templ + self.temph) / 2.0

    @property
    def is_airborne(self) -> bool:
        return self.h > 10


# Type aliases for the field converters
_INT_FIELDS   = {'pitch', 'roll', 'yaw', 'vgx', 'vgy', 'vgz',
                 'templ', 'temph', 'tof', 'h', 'bat'}
_FLOAT_FIELDS = {'baro', 'agx', 'agy', 'agz'}


def parse_state(raw: str) -> Optional[DroneState]:
    """
    Parse a raw Tello state string into a DroneState object.

    Returns None if the string is malformed.
    """
    if not raw or not raw.strip():
        return None

    state = DroneState()
    try:
        for pair in raw.strip().split(';'):
            pair = pair.strip()
            if ':' not in pair:
                continue
            key, _, val = pair.partition(':')
            key = key.strip()
            val = val.strip()
            if not val:
                continue

            if key in _INT_FIELDS:
                setattr(state, key, int(float(val)))
            elif key in _FLOAT_FIELDS:
                setattr(state, key, float(val))
    except (ValueError, AttributeError):
        return None

    return state
