"""
src/ui/pages.py
The three pages of the main window:

  FlyPage   - full-bleed camera + fighter HUD + live mission map + progress strip + action deck
  PlanPage  - waypoint planner (map, table, altitude profile, pattern tools)
  LogsPage  - flight log
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QDoubleSpinBox, QFileDialog, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QMessageBox,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from src.drone.mission import estimate, outside_fence
from src.ui import theme
from src.ui.mission_model import MissionModel
from src.ui.widgets.camera_widget import CameraWidget
from src.ui.widgets.fighter_hud import FighterHUDWidget
from src.ui.widgets.flight_log import FlightLogPanel
from src.ui.widgets.glass import GlassPanel
from src.ui.widgets.mission_map import MissionMapWidget
from src.ui.widgets.mission_widgets import AltitudeProfile, MissionStatusList, MissionStrip, mmss
from src.ui.widgets.rc_stick_widget import RCStickWidget
from src.ui.widgets.sparkline_widget import SparklineCard
from src.ui.widgets.topbar import TopBar
from src.ui.widgets.vehicle_panel import KvCell, VehiclePanel


def _btn(text: str, name: str = "", parent=None) -> QPushButton:
    b = QPushButton(text, parent)
    if name:
        b.setObjectName(name)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return b


def _muted(text: str) -> QLabel:
    l = QLabel(text)
    l.setObjectName("muted")
    return l


class Page(QWidget):
    """Dark gradient page background (used by the non-video pages)."""

    def paintEvent(self, event):
        p = QPainter(self)
        g = QLinearGradient(0, 0, 0, self.height())
        g.setColorAt(0, QColor(0x0a, 0x14, 0x1e))
        g.setColorAt(1, QColor(0x05, 0x08, 0x0d))
        p.fillRect(self.rect(), g)


# ══════════════════════════════════════════════════════════════════════
#  FLY
# ══════════════════════════════════════════════════════════════════════

class FlyPage(CameraWidget):
    """Camera canvas with the glass cockpit laid out on top of it."""

    def __init__(self, model: MissionModel, pose, parent=None):
        super().__init__(parent)
        self.topbar = TopBar(0)

        g = QGridLayout(self)
        g.setContentsMargins(12, 12, 12, 12)
        g.setSpacing(12)
        g.addWidget(self.topbar, 0, 0, 1, 3)

        # left column: vehicle + flight data
        left = QWidget()
        left.setFixedWidth(250)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(12)
        self.vehicle = VehiclePanel()
        lv.addWidget(self.vehicle)
        self.fdata = GlassPanel("Flight data", "SPD · ALT · PITCH")
        self.fdata.setMinimumHeight(110)
        self.trace = SparklineCard("", width=None, height=None, framed=False)
        self.trace.add_series("SPD", theme.ACCENT, 0, 100, max_len=90)
        self.trace.add_series("ALT", theme.WARN, 0, 300, max_len=90)
        self.trace.add_series("ATT", theme.OK, -35, 35, max_len=90)
        self.fdata.body.addWidget(self.trace)
        lv.addWidget(self.fdata, 1)
        g.addWidget(left, 1, 0)

        # centre: fighter HUD
        self.hud = FighterHUDWidget()
        g.addWidget(self.hud, 1, 1)

        # right: live mission
        self.live = GlassPanel("Live mission", "NO MISSION")
        self.live.setFixedWidth(380)
        self.map = MissionMapWidget(model, pose, editable=False, live=True, labels=True,
                                    show_progress=True, auto_fit=True)
        self.status = MissionStatusList(model, pose)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_skip = _btn("⏭ SKIP WP")
        self.btn_abort = _btn("■ ABORT", "danger")
        self.btn_edit = _btn("EDIT ›")
        row.addWidget(self.btn_skip)
        row.addWidget(self.btn_abort)
        row.addStretch(1)
        row.addWidget(self.btn_edit)
        self.live.body.addWidget(self.map, 1)
        self.live.body.addWidget(self.status)
        self.live.body.addLayout(row)
        g.addWidget(self.live, 1, 2)

        # progress strip
        strip = GlassPanel("", "")
        strip.setFixedHeight(84)
        strip.body.setContentsMargins(6, 4, 6, 4)
        strip.body.addWidget(MissionStrip(model, pose))
        g.addWidget(strip, 2, 0, 1, 3)

        # action deck
        deck = GlassPanel("", "")
        deck.setFixedHeight(62)
        deck.body.setContentsMargins(14, 8, 14, 8)
        drow = QHBoxLayout()
        drow.setSpacing(8)
        self.stick_l = RCStickWidget(size=44)
        self.stick_r = RCStickWidget(size=44)
        self.btn_connect   = _btn("⚡ UPLINK")
        self.btn_takeoff   = _btn("▲ LAUNCH", "ok")
        self.btn_land      = _btn("▼ RTB LAND", "warn")
        self.btn_rst_pos   = _btn("⌖ RESET HOME")
        self.btn_ai        = _btn("🎯 AI TRACK: ON")
        self.btn_plot      = _btn("📈 DATA: ON")
        self.btn_start     = _btn("▶ START MISSION", "primary")
        self.btn_emergency = _btn("⚠ CUTOFF", "danger")
        drow.addWidget(self.stick_l)
        for b in (self.btn_connect, self.btn_takeoff, self.btn_land, self.btn_rst_pos,
                  self.btn_ai, self.btn_plot, self.btn_start, self.btn_emergency):
            drow.addWidget(b)
        drow.addWidget(self.stick_r)
        deck.body.addLayout(drow)
        g.addWidget(deck, 3, 0, 1, 3, Qt.AlignmentFlag.AlignHCenter)

        g.setColumnStretch(1, 1)
        g.setRowStretch(1, 1)

    def set_sticks(self, lr: int, fb: int, ud: int, yaw: int):
        self.stick_l.set_values(yaw / 100.0, ud / 100.0)
        self.stick_r.set_values(lr / 100.0, fb / 100.0)


# ══════════════════════════════════════════════════════════════════════
#  PLAN
# ══════════════════════════════════════════════════════════════════════

class PlanPage(Page):
    start_requested = Signal()

    def __init__(self, model: MissionModel, pose, parent=None):
        super().__init__(parent)
        from src.ui.widgets.waypoint_table import WaypointTable

        self.m = model
        self.topbar = TopBar(1)
        self.btn_load = _btn("LOAD")
        self.btn_save = _btn("SAVE")
        self.btn_start = _btn("▶ START MISSION", "primary")
        for b in (self.btn_load, self.btn_save, self.btn_start):
            self.topbar.add_right(b)
        self.btn_load.clicked.connect(self._load)
        self.btn_save.clicked.connect(self._save)
        self.btn_start.clicked.connect(self.start_requested)

        g = QGridLayout(self)
        g.setContentsMargins(12, 12, 12, 12)
        g.setSpacing(12)
        g.addWidget(self.topbar, 0, 0, 1, 3)

        # tools
        tools = GlassPanel("Commands")
        tools.setFixedWidth(210)
        t = tools.body
        t.addWidget(_muted("ADD COMMAND"))
        for cmd, label in (("GO", "＋ GO (XYZ)"), ("ROTATE", "⟳ ROTATE"), ("HOVER", "⏸ HOVER"),
                           ("FLIP", "↻ FLIP"), ("LAND", "⬇ LAND")):
            b = _btn(label, "tool")
            b.clicked.connect(lambda _=False, c=cmd: self.m.add_command(c))
            t.addWidget(b)
        t.addWidget(_muted("PATTERN"))
        for label, fn in (("◯ Orbit", self._orbit), ("▭ Square", self._square), ("▦ Grid scan", self._grid)):
            b = _btn(label, "tool")
            b.clicked.connect(fn)
            t.addWidget(b)
        t.addWidget(_muted("DEFAULTS"))
        self.sp_alt = self._spin(QDoubleSpinBox(), 0.2, 5.0, model.default_alt_cm / 100, " m alt", 0.1, 1)
        self.sp_spd = self._spin(QSpinBox(), 10, 100, model.default_speed, " cm/s", 5)
        self.sp_fence = self._spin(QDoubleSpinBox(), 3, 100, model.geofence_cm / 100, " m fence", 1, 0)
        self.sp_alt.valueChanged.connect(lambda v: setattr(self.m, "default_alt_cm", v * 100))
        self.sp_spd.valueChanged.connect(lambda v: setattr(self.m, "default_speed", int(v)))
        self.sp_fence.valueChanged.connect(self._fence)
        for s in (self.sp_alt, self.sp_spd, self.sp_fence):
            t.addWidget(s)
        t.addStretch(1)
        b_fit = _btn("FIT VIEW")
        b_clr = _btn("CLEAR MISSION", "danger")
        t.addWidget(b_fit)
        t.addWidget(b_clr)
        b_clr.clicked.connect(self._clear)
        hint = QLabel("Click map: add waypoint\nDrag: move\nRight-click: delete\nWheel: zoom · MMB: pan")
        hint.setObjectName("muted")
        t.addWidget(hint)
        g.addWidget(tools, 1, 0, 2, 1)

        # map
        mp = GlassPanel("Mission map", "NO GPS · LOCAL METRIC FRAME")
        self.map = MissionMapWidget(model, pose, editable=True, live=True, labels=True, show_progress=True)
        mp.body.addWidget(self.map)
        b_fit.clicked.connect(lambda: self.map.fit())
        g.addWidget(mp, 1, 1)

        # table
        tp = GlassPanel("Waypoints", "double-click a cell to edit")
        tp.setFixedWidth(490)
        tp.body.setContentsMargins(4, 28, 4, 6)
        tp.body.addWidget(WaypointTable(model))
        g.addWidget(tp, 1, 2)

        # bottom: altitude profile + stats
        bt = GlassPanel("Altitude profile", "ALT vs PATH DISTANCE")
        bt.setFixedHeight(160)
        row = QHBoxLayout()
        row.addWidget(AltitudeProfile(model, pose), 1)
        stats = QGridLayout()
        stats.setSpacing(6)
        self._st = {}
        for i, (k, title) in enumerate((("dist", "PATH"), ("time", "EST. TIME"),
                                        ("bat", "EST. BATTERY"), ("fence", "GEOFENCE"))):
            c = KvCell(title)
            self._st[k] = c.v
            stats.addWidget(c, i // 2, i % 2)
        sw = QWidget()
        sw.setFixedWidth(300)
        sw.setLayout(stats)
        row.addWidget(sw)
        bt.body.addLayout(row)
        g.addWidget(bt, 2, 1, 1, 2)

        g.setColumnStretch(1, 1)
        g.setRowStretch(1, 1)
        model.changed.connect(self._update_stats)
        self._update_stats()

    @staticmethod
    def _spin(w, lo, hi, val, suffix, step, decimals=None):
        w.setRange(lo, hi)
        if decimals is not None:
            w.setDecimals(decimals)
        w.setSingleStep(step)
        w.setValue(val)
        w.setSuffix(suffix)
        w.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        return w

    def _fence(self, v: float):
        self.m.geofence_cm = v * 100
        self.m.changed.emit()

    def _update_stats(self):
        length, secs, bat = estimate(self.m.items)
        self._st["dist"].setText(f"{length / 100:.1f} m")
        self._st["time"].setText(mmss(secs))
        self._st["bat"].setText(f"~{bat:.0f}%")
        out = outside_fence(self.m.items, self.m.geofence_cm)
        self._st["fence"].setText("OK" if not out else f"{len(out)} OUT")
        self._st["fence"].setStyleSheet(f"color: {(theme.OK if not out else theme.ALERT).name()};")

    # patterns
    def _square(self):
        v, ok = QInputDialog.getDouble(self, "Square", "Side length (m):", 1.5, 0.3, 20.0, 1)
        if ok:
            self.m.add_square(v * 100)

    def _orbit(self):
        v, ok = QInputDialog.getDouble(self, "Orbit", "Radius (m):", 1.2, 0.3, 10.0, 1)
        if ok:
            self.m.add_orbit(v * 100)

    def _grid(self):
        w, ok = QInputDialog.getDouble(self, "Grid scan", "Width (m):", 3.0, 0.5, 20.0, 1)
        if not ok:
            return
        sp, ok = QInputDialog.getDouble(self, "Grid scan", "Row spacing (m):", 0.8, 0.3, 5.0, 1)
        if not ok:
            return
        rows, ok = QInputDialog.getInt(self, "Grid scan", "Rows:", 4, 2, 20)
        if ok:
            self.m.add_grid(w * 100, sp * 100, rows)

    def _clear(self):
        if QMessageBox.question(self, "Clear mission", "Remove all waypoints?") == QMessageBox.StandardButton.Yes:
            self.m.reset()

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save mission", "mission.json", "Mission (*.json)")
        if path:
            try:
                self.m.save(path)
            except OSError as e:
                QMessageBox.warning(self, "Save failed", str(e))

    def _load(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load mission", "", "Mission (*.json)")
        if path:
            try:
                self.m.load(path)
                self.sp_fence.setValue(self.m.geofence_cm / 100)
                self.map.fit()
            except (OSError, ValueError, KeyError) as e:
                QMessageBox.warning(self, "Load failed", f"Invalid mission file:\n{e}")


# ══════════════════════════════════════════════════════════════════════
#  LOGS
# ══════════════════════════════════════════════════════════════════════

class LogsPage(Page):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.topbar = TopBar(2)
        g = QGridLayout(self)
        g.setContentsMargins(12, 12, 12, 12)
        g.setSpacing(12)
        g.addWidget(self.topbar, 0, 0)
        self.log = FlightLogPanel(None, width=None, height=None)
        g.addWidget(self.log, 1, 0)
        g.setRowStretch(1, 1)
