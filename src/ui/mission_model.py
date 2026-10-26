"""
src/ui/mission_model.py
Qt model shared by the planner page, the live mission map, the strip and the tables.
"""

import json
import math
from typing import List, Optional

from PySide6.QtCore import QObject, Signal

from src.drone.mission import (
    Waypoint, DEFAULT_ALT_CM, DEFAULT_SPEED, default_param, cumulative, seg_length,
)


class MissionModel(QObject):
    changed           = Signal()
    selection_changed = Signal(int)
    progress_changed  = Signal()

    IDLE, RUNNING, DONE = 0, 1, 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.geofence_cm = 1500.0
        self.default_alt_cm = DEFAULT_ALT_CM
        self.default_speed = DEFAULT_SPEED
        self.state = self.IDLE
        self.target = 0          # index of the item being flown to (valid while RUNNING)
        self.selected = -1
        self.items: List[Waypoint] = []
        self.reset()

    # ── Basic edits ──────────────────────────────────────────────────────

    @property
    def locked(self) -> bool:
        """The plan cannot be edited while the drone is flying it."""
        return self.state == self.RUNNING

    def reset(self):
        if self.locked:
            return
        self.items = [Waypoint("TAKEOFF", 0, 0, self.default_alt_cm),
                      Waypoint("LAND", 0, 0, 0)]
        self.selected = -1
        self.state, self.target = self.IDLE, 0
        self.changed.emit()
        self.progress_changed.emit()

    def set_items(self, items: List[Waypoint]):
        if self.locked:
            return
        if not items or items[0].cmd != "TAKEOFF":
            items = [Waypoint("TAKEOFF", 0, 0, self.default_alt_cm)] + list(items)
        self.items = items
        self.selected = -1
        self.state, self.target = self.IDLE, 0
        self.changed.emit()
        self.progress_changed.emit()

    def _insert_index(self) -> int:
        idx = self.selected + 1 if self.selected >= 0 else len(self.items)
        if self.items[-1].cmd == "LAND" and idx >= len(self.items):
            idx = len(self.items) - 1
        return max(1, idx)

    def insert_many(self, idx: int, wps: List[Waypoint]):
        if self.locked:
            return
        for k, w in enumerate(wps):
            self.items.insert(idx + k, w)
        self.selected = idx + len(wps) - 1
        self.changed.emit()
        self.selection_changed.emit(self.selected)

    def _prev(self, idx: int) -> Waypoint:
        return self.items[max(0, idx - 1)]

    def add_go(self, x_cm: float, y_cm: float):
        idx = len(self.items) - (1 if self.items[-1].cmd == "LAND" else 0)   # before the final LAND
        alt = self._prev(idx).alt or self.default_alt_cm
        self.insert_many(idx, [Waypoint("GO", round(x_cm, 1), round(y_cm, 1), alt, str(self.default_speed))])

    def add_command(self, cmd: str):
        idx = self._insert_index()
        p = self._prev(idx)
        alt = 0.0 if cmd == "LAND" else (p.alt or self.default_alt_cm)
        self.insert_many(idx, [Waypoint(cmd, p.x, p.y, alt, default_param(cmd))])

    def remove(self, i: int):
        if self.locked or i <= 0 or i >= len(self.items):
            return
        del self.items[i]
        self.selected = min(self.selected, len(self.items) - 1) if self.selected >= 0 else -1
        self.changed.emit()
        self.selection_changed.emit(self.selected)

    def duplicate(self, i: int):
        if 0 < i < len(self.items):
            self.insert_many(i + 1, [Waypoint(**self.items[i].to_dict())])

    def move(self, i: int, x_cm: float, y_cm: float):
        if self.locked or i <= 0 or i >= len(self.items):
            return
        self.items[i].x, self.items[i].y = round(x_cm, 1), round(y_cm, 1)
        self.changed.emit()

    def update(self, i: int, **kw):
        if self.locked or not (0 <= i < len(self.items)):
            return
        w = self.items[i]
        for k, v in kw.items():
            if k == "cmd" and i == 0:
                continue
            setattr(w, k, v)
        self.changed.emit()

    def select(self, i: int):
        if i != self.selected:
            self.selected = i
            self.selection_changed.emit(i)

    # ── Patterns ─────────────────────────────────────────────────────────

    def _pattern_base(self):
        idx = self._insert_index()
        b = self._prev(idx)
        return idx, b

    def add_square(self, side_cm: float):
        idx, b = self._pattern_base()
        s, sp = side_cm, str(self.default_speed)
        pts = [(b.x + s, b.y), (b.x + s, b.y + s), (b.x, b.y + s), (b.x, b.y)]
        self.insert_many(idx, [Waypoint("GO", x, y, b.alt or self.default_alt_cm, sp) for x, y in pts])

    def add_orbit(self, radius_cm: float, n: int = 8):
        idx, b = self._pattern_base()
        sp = str(self.default_speed)
        cx, cy = b.x, b.y + radius_cm      # circle centre ahead of the last point
        pts = []
        for k in range(n + 1):
            a = math.pi + 2 * math.pi * k / n
            pts.append((cx + radius_cm * math.sin(a), cy + radius_cm * math.cos(a)))
        self.insert_many(idx, [Waypoint("GO", x, y, b.alt or self.default_alt_cm, sp) for x, y in pts[1:]])

    def add_grid(self, width_cm: float, spacing_cm: float, rows: int):
        idx, b = self._pattern_base()
        sp = str(self.default_speed)
        # lawnmower: sweep right on even rows, left on odd rows
        pts = []
        for r in range(rows):
            y = b.y + r * spacing_cm
            if r % 2 == 0:
                pts += [(b.x + width_cm, y)]
            else:
                pts += [(b.x, y)]
            if r < rows - 1:
                pts += [(pts[-1][0], y + spacing_cm)]
        self.insert_many(idx, [Waypoint("GO", x, y, b.alt or self.default_alt_cm, sp) for x, y in pts])

    # ── Progress ─────────────────────────────────────────────────────────

    def set_state(self, state: int):
        self.state = state
        if state != self.RUNNING:
            self.target = 0
        self.progress_changed.emit()

    def set_target(self, idx: int):
        self.target = idx
        self.progress_changed.emit()

    def progress_fraction(self, x_cm: float, y_cm: float) -> float:
        """0..1 along the planned horizontal path based on the drone position."""
        if self.state == self.DONE:
            return 1.0
        if self.state != self.RUNNING:
            return 0.0
        cum, total = cumulative(self.items)
        if total <= 0:
            return 0.0
        t = max(1, min(self.target, len(self.items) - 1))
        a = self.items[t - 1]
        seg = seg_length(a, self.items[t])
        into = min(seg, math.hypot(x_cm - a.x, y_cm - a.y))
        return max(0.0, min(1.0, (cum[t - 1] + into) / total))

    # ── Persistence ──────────────────────────────────────────────────────

    def save(self, path: str):
        data = {"version": 1, "geofence_cm": self.geofence_cm,
                "items": [w.to_dict() for w in self.items]}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.geofence_cm = float(data.get("geofence_cm", self.geofence_cm))
        self.set_items([Waypoint.from_dict(d) for d in data.get("items", [])])
