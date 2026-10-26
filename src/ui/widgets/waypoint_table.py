"""
src/ui/widgets/waypoint_table.py
Mission-Planner style waypoint grid, bound to a MissionModel.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHeaderView, QMenu, QStyle, QStyledItemDelegate, QTableWidget,
    QTableWidgetItem,
)

from src.drone.mission import CMDS, default_param, seg_length, bearing_deg
from src.ui import theme
from src.ui.mission_model import MissionModel

COLS = ["#", "CMD", "X (m)", "Y (m)", "ALT (m)", "PARAM", "DIST (m)", "HDG"]
MOVES = ("GO", "TAKEOFF", "LAND")     # commands that carry a position


class _NoFocusRect(QStyledItemDelegate):
    """Selected rows already highlight; drop the per-cell focus rectangle."""

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.state &= ~QStyle.StateFlag.State_HasFocus


class WaypointTable(QTableWidget):
    def __init__(self, model: MissionModel, parent=None):
        super().__init__(0, len(COLS), parent)
        self.m = model
        self._busy = False
        self.setItemDelegate(_NoFocusRect(self))

        self.setHorizontalHeaderLabels(COLS)
        self.verticalHeader().hide()
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.setShowGrid(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hh = self.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(1, 96)                 # fits the CMD combo box
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        hh.setStretchLastSection(False)

        self.m.changed.connect(self._on_model_changed)
        self.m.selection_changed.connect(self._sync_selection)
        self.itemChanged.connect(self._on_item_changed)
        self.itemSelectionChanged.connect(self._on_selection)
        self.customContextMenuRequested.connect(self._menu)
        self._rebuild()

    # ── Model → table ────────────────────────────────────────────────────

    def _on_model_changed(self):
        cmds_now = [self.cellWidget(r, 1).currentText() if self.cellWidget(r, 1) else "TAKEOFF"
                    for r in range(self.rowCount())]
        if self.rowCount() == len(self.m.items) and cmds_now == [w.cmd for w in self.m.items]:
            self._refresh_values()
        else:
            self._rebuild()

    def _item(self, text: str, editable: bool, align=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft):
        it = QTableWidgetItem(text)
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if editable:
            flags |= Qt.ItemFlag.ItemIsEditable
        it.setFlags(flags)
        it.setTextAlignment(align)
        if not editable:
            it.setForeground(QColor(theme.MUTED if text in ("-", "") else theme.TEXT))
        return it

    def _row_values(self, i: int):
        w = self.m.items[i]
        prev = self.m.items[i - 1] if i else None
        dist = f"{seg_length(prev, w) / 100:.1f}" if prev and w.cmd in MOVES else "-"
        hdg = (f"{bearing_deg(prev, w):.0f}" if prev and w.cmd == "GO" and seg_length(prev, w) > 10 else "-")
        pos_ok = w.cmd in MOVES and i > 0
        return [
            ("H" if i == 0 else str(i), False),
            None,                                           # CMD combo
            (f"{w.x / 100:.2f}", pos_ok and w.cmd == "GO"),
            (f"{w.y / 100:.2f}", pos_ok and w.cmd == "GO"),
            (f"{w.alt / 100:.2f}", w.cmd in ("GO", "TAKEOFF")),
            (w.param or "-", w.cmd in ("GO", "ROTATE", "HOVER", "FLIP")),
            (dist, False),
            (hdg, False),
        ]

    def _rebuild(self):
        self._busy = True
        self.clearContents()
        self.setRowCount(len(self.m.items))
        for i, w in enumerate(self.m.items):
            for c, v in enumerate(self._row_values(i)):
                if v is None:
                    if i == 0:
                        self.setItem(i, c, self._item("TAKEOFF", False))
                    else:
                        cb = QComboBox()
                        cb.addItems([c_ for c_ in CMDS if c_ != "TAKEOFF"])
                        cb.setCurrentText(w.cmd)
                        cb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                        cb.currentTextChanged.connect(lambda txt, row=i: self._on_cmd(row, txt))
                        self.setCellWidget(i, c, cb)
                else:
                    self.setItem(i, c, self._item(v[0], v[1]))
        self._busy = False
        self._sync_selection(self.m.selected)

    def _refresh_values(self):
        self._busy = True
        for i in range(self.rowCount()):
            for c, v in enumerate(self._row_values(i)):
                if v is None:
                    continue
                it = self.item(i, c)
                if it is not None and it.text() != v[0]:
                    it.setText(v[0])
        self._busy = False

    def _sync_selection(self, idx: int):
        self._busy = True
        if 0 <= idx < self.rowCount():
            self.selectRow(idx)
        else:
            self.clearSelection()
        self._busy = False

    # ── Table → model ────────────────────────────────────────────────────

    def _on_selection(self):
        if self._busy:
            return
        rows = self.selectionModel().selectedRows()
        self.m.select(rows[0].row() if rows else -1)

    def _on_cmd(self, row: int, cmd: str):
        if self._busy:
            return
        w = self.m.items[row]
        prev = self.m.items[row - 1]
        self.m.update(row, cmd=cmd, param=default_param(cmd),
                      x=prev.x if cmd != "GO" else w.x, y=prev.y if cmd != "GO" else w.y,
                      alt=0.0 if cmd == "LAND" else (w.alt or prev.alt))

    def _on_item_changed(self, it: QTableWidgetItem):
        if self._busy:
            return
        r, c, txt = it.row(), it.column(), it.text().strip()
        try:
            if c == 2:
                self.m.update(r, x=float(txt) * 100)
            elif c == 3:
                self.m.update(r, y=float(txt) * 100)
            elif c == 4:
                self.m.update(r, alt=max(0.0, float(txt)) * 100)
            elif c == 5:
                self.m.update(r, param=txt)
        except ValueError:
            pass
        self._refresh_values()          # revert invalid / rejected input

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Delete and self.currentRow() > 0:
            self.m.remove(self.currentRow())
            return
        super().keyPressEvent(e)

    def _menu(self, pos):
        row = self.rowAt(pos.y())
        if row < 0:
            return
        menu = QMenu(self)
        a_dup = menu.addAction("Duplicate")
        a_del = menu.addAction("Delete")
        a_dup.setEnabled(row > 0)
        a_del.setEnabled(row > 0)
        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen == a_dup:
            self.m.duplicate(row)
        elif chosen == a_del:
            self.m.remove(row)
