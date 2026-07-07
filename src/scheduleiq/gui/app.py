"""ScheduleIQ desktop application (PySide6).

Workflow mirrors the analyst's intake process:
  1. Drag one or more .xer / .xml / .mpp files in (or Add Files).
  2. The app auto-orders them by data date and flags files that do not look
     like the same project; the analyst confirms Series vs Benchmark mode.
  3. Optional: adjust threshold overrides (defaults = published standards;
     overrides are marked in every output).
  4. Run — results tree with drill-down to offending activities; one click
     opens the output folder with the Word/PDF report and Excel workbooks.
"""
from __future__ import annotations

import os
import sys
import traceback

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox,
                               QProgressBar, QPushButton, QRadioButton,
                               QSplitter, QTableWidget, QTableWidgetItem,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from .. import __version__
from ..ingest import SUPPORTED, load_many
from ..metrics.engine import load_matrix

TEAL = "#1F6F7B"
STATUS_COLOR = {"FAIL": "#F4B084", "WARNING": "#FFE699", "PASS": "#C6E0B4",
                "INFO": "#DDEBF7", "N/A": "#EDEDED", "NOT EVALUATED": "#EDEDED"}


class RunWorker(QThread):
    progressed = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, paths, out_dir, overrides, paper, make_pdf, benchmark):
        super().__init__()
        self.paths, self.out_dir = paths, out_dir
        self.overrides, self.paper = overrides, paper
        self.make_pdf, self.benchmark = make_pdf, benchmark

    def run(self):
        try:
            import json
            import tempfile
            from ..runner import run
            profile = None
            if self.overrides:
                tf = tempfile.NamedTemporaryFile("w", suffix=".json",
                                                 delete=False)
                json.dump(self.overrides, tf)
                tf.close()
                profile = tf.name
            rr = run(self.paths, self.out_dir, profile=profile,
                     paper=self.paper, make_pdf=self.make_pdf,
                     benchmark=self.benchmark,
                     progress=self.progressed.emit)
            self.finished_ok.emit(rr)
        except Exception:
            self.failed.emit(traceback.format_exc())


class ThresholdDialog(QDialog):
    """Threshold profile editor: standard defaults, analyst overrides."""

    def __init__(self, overrides: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Threshold Profile — standard defaults with overrides")
        self.resize(900, 600)
        self.overrides = dict(overrides)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Defaults are the published standard values (see the metric matrix).  "
            "Enter a value in the Override column to change a threshold for this "
            "run; overrides are recorded in every report and workbook."))
        self.table = QTableWidget()
        matrix = load_matrix()
        rows = [c for c in matrix if c.threshold is not None]
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Check", "Unit", "Standard default", "Override"])
        self.table.setRowCount(len(rows))
        for i, c in enumerate(rows):
            for j, val in enumerate([c.id, c.name, c.unit,
                                     f"{c.threshold:g}"]):
                it = QTableWidgetItem(val)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(i, j, it)
            ov = self.overrides.get(c.id)
            self.table.setItem(i, 4, QTableWidgetItem(
                "" if ov is None else f"{ov:g}"))
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        lay.addWidget(self.table)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def result_overrides(self) -> dict:
        out = {}
        for i in range(self.table.rowCount()):
            txt = (self.table.item(i, 4).text() or "").strip() \
                if self.table.item(i, 4) else ""
            if txt:
                try:
                    out[self.table.item(i, 0).text()] = float(txt)
                except ValueError:
                    continue
        return out


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"ScheduleIQ v{__version__} — Schedule Quality, "
                            "Health, and Trend Analysis")
        self.resize(1240, 800)
        self.overrides: dict = {}
        self.out_dir = os.path.join(os.path.expanduser("~"), "ScheduleIQ Output")
        self._build_ui()
        self.setAcceptDrops(True)

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        split = QSplitter()
        self.setCentralWidget(split)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel("<b>Schedule files</b> — drag .xer / .xml / .mpp "
                            "here; auto-ordered by data date"))
        self.file_list = QListWidget()
        ll.addWidget(self.file_list, 1)
        row = QHBoxLayout()
        for text, fn in [("Add Files…", self.add_files),
                         ("Remove", self.remove_selected),
                         ("Clear", self.file_list.clear)]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        ll.addLayout(row)
        self.warn_label = QLabel("")
        self.warn_label.setWordWrap(True)
        self.warn_label.setStyleSheet("color: #C55A11;")
        ll.addWidget(self.warn_label)

        mode_row = QHBoxLayout()
        self.mode_series = QRadioButton("Series (updates of one project — "
                                        "trend + change analysis)")
        self.mode_series.setChecked(True)
        self.mode_bench = QRadioButton("Benchmark (separate projects side by side)")
        mode_row.addWidget(self.mode_series)
        mode_row.addWidget(self.mode_bench)
        ll.addLayout(mode_row)

        opt_row = QHBoxLayout()
        self.paper = QComboBox()
        self.paper.addItems(["letter", "a4"])
        self.pdf_cb = QCheckBox("PDF (via Word)")
        self.pdf_cb.setChecked(True)
        thr_btn = QPushButton("Thresholds…")
        thr_btn.clicked.connect(self.edit_thresholds)
        out_btn = QPushButton("Output Folder…")
        out_btn.clicked.connect(self.pick_out_dir)
        for w in (QLabel("Paper:"), self.paper, self.pdf_cb, thr_btn, out_btn):
            opt_row.addWidget(w)
        ll.addLayout(opt_row)

        self.run_btn = QPushButton("Run Analysis")
        self.run_btn.setStyleSheet(
            f"background:{TEAL}; color:white; font-weight:bold; padding:8px;")
        self.run_btn.clicked.connect(self.run_analysis)
        ll.addWidget(self.run_btn)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        ll.addWidget(self.progress)
        self.status_label = QLabel("")
        ll.addWidget(self.status_label)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(QLabel("<b>Results</b> — double-click a check to see "
                            "offending activities"))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Check / Finding", "Value", "Threshold",
                                   "Status", "Result"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        rl.addWidget(self.tree, 1)
        self.open_btn = QPushButton("Open Output Folder")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self.open_output)
        rl.addWidget(self.open_btn)

        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([460, 780])

        m = self.menuBar().addMenu("&Help")
        about = QAction("About ScheduleIQ", self)
        about.triggered.connect(lambda: QMessageBox.about(
            self, "ScheduleIQ",
            f"ScheduleIQ v{__version__}\n\nSchedule quality, health, trend, "
            "and change analysis for Primavera P6 (.xer), Microsoft Project "
            "(.mpp/.xml).\n\nEvery check is documented in the Metric & "
            "Heuristic Matrix with its source standard and default threshold."))
        m.addAction(about)

    # ------------------------------------------------------------- files
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        self._add_paths(paths)

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add schedule files", "",
            "Schedules (*.xer *.xml *.mpp);;All files (*)")
        self._add_paths(paths)

    def _add_paths(self, paths):
        existing = {self.file_list.item(i).data(Qt.UserRole)
                    for i in range(self.file_list.count())}
        for p in paths:
            if p and os.path.splitext(p)[1].lower() in SUPPORTED \
                    and p not in existing:
                it = QListWidgetItem(os.path.basename(p))
                it.setData(Qt.UserRole, p)
                self.file_list.addItem(it)
        self._refresh_order()

    def remove_selected(self):
        for it in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(it))
        self._refresh_order()

    def _refresh_order(self):
        """Parse headers, auto-order by data date, surface warnings."""
        paths = [self.file_list.item(i).data(Qt.UserRole)
                 for i in range(self.file_list.count())]
        if not paths:
            self.warn_label.setText("")
            return
        try:
            from ..trend.series import order_and_validate
            schedules = load_many(paths)
            ordered, warnings = order_and_validate(schedules)
            self.file_list.clear()
            for s in ordered:
                path = next(p for p in paths
                            if os.path.basename(p) == s.source_file)
                it = QListWidgetItem(f"{s.source_file}   —   {s.label()}")
                it.setData(Qt.UserRole, path)
                self.file_list.addItem(it)
            self.warn_label.setText(
                "\n".join(w.message for w in warnings)
                if warnings else "Files ordered by data date — confirm before "
                                 "running." if len(ordered) > 1 else "")
        except Exception as e:
            self.warn_label.setText(f"Could not pre-read a file: {e}")

    # ------------------------------------------------------------ options
    def edit_thresholds(self):
        dlg = ThresholdDialog(self.overrides, self)
        if dlg.exec():
            self.overrides = dlg.result_overrides()
            self.status_label.setText(
                f"{len(self.overrides)} threshold override(s) active."
                if self.overrides else "Standard default thresholds.")

    def pick_out_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Output folder",
                                             self.out_dir)
        if d:
            self.out_dir = d
            self.status_label.setText(f"Output folder: {d}")

    # --------------------------------------------------------------- run
    def run_analysis(self):
        paths = [self.file_list.item(i).data(Qt.UserRole)
                 for i in range(self.file_list.count())]
        if not paths:
            QMessageBox.warning(self, "ScheduleIQ", "Add at least one "
                                "schedule file.")
            return
        self.run_btn.setEnabled(False)
        self.progress.show()
        self.tree.clear()
        self.worker = RunWorker(paths, self.out_dir, self.overrides,
                                self.paper.currentText(),
                                self.pdf_cb.isChecked(),
                                self.mode_bench.isChecked())
        self.worker.progressed.connect(self.status_label.setText)
        self.worker.finished_ok.connect(self.show_results)
        self.worker.failed.connect(self.show_error)
        self.worker.start()

    def show_error(self, tb: str):
        self.progress.hide()
        self.run_btn.setEnabled(True)
        QMessageBox.critical(self, "ScheduleIQ — run failed", tb[-2000:])

    def show_results(self, rr):
        self.progress.hide()
        self.run_btn.setEnabled(True)
        self.open_btn.setEnabled(True)
        sa = rr.analysis
        latest = sa.assessments[-1]
        self.status_label.setText(
            f"Done.  Latest health score {latest.health_score:.0f}/100 — "
            f"{latest.counts.get('FAIL', 0)} FAIL, "
            f"{latest.counts.get('WARNING', 0)} WARNING.  "
            + (" ".join(rr.messages)[:300] if rr.messages else ""))
        for s, a in zip(sa.schedules, sa.assessments):
            top = QTreeWidgetItem([f"{s.label()} — health "
                                   f"{a.health_score:.0f}/100"])
            self.tree.addTopLevelItem(top)
            for res in a.results:
                if res.status in ("N/A",):
                    continue
                row = QTreeWidgetItem([
                    f"{res.check.id}  {res.check.name}", res.display_value,
                    "—" if res.threshold_applied is None
                    else f"{res.threshold_applied:g}",
                    res.status, res.narrative])
                for col in range(5):
                    row.setBackground(col, QColor(
                        STATUS_COLOR.get(res.status, "#FFFFFF")))
                for f in res.findings[:500]:
                    row.addChild(QTreeWidgetItem(
                        [f.object_id, "", "", "", f"{f.object_name}  "
                                                  f"{f.detail}".strip()]))
                top.addChild(row)
            top.setExpanded(False)
        if sa.series_results:
            top = QTreeWidgetItem(["Series metrics (trend & change)"])
            self.tree.addTopLevelItem(top)
            for res in sa.series_results:
                row = QTreeWidgetItem([
                    f"{res.check.id}  {res.check.name}", res.display_value,
                    "—" if res.threshold_applied is None
                    else f"{res.threshold_applied:g}",
                    res.status, res.narrative])
                for col in range(5):
                    row.setBackground(col, QColor(
                        STATUS_COLOR.get(res.status, "#FFFFFF")))
                for f in res.findings[:500]:
                    row.addChild(QTreeWidgetItem(
                        [f.object_id, "", "", "", f.detail]))
                top.addChild(row)
            top.setExpanded(True)

    def open_output(self):
        import subprocess
        if sys.platform == "win32":
            os.startfile(self.out_dir)          # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", self.out_dir])
        else:
            subprocess.run(["xdg-open", self.out_dir])


def run_gui() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ScheduleIQ")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())
