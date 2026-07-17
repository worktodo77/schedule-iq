"""ScheduleIQ premium desktop application (PySide6 / Qt Widgets).

This module is deliberately presentation-only.  It invokes ``runner.run`` with
the same arguments as the CLI and renders existing result objects without
altering any check, metric, score, or report computation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import traceback

from PySide6.QtCore import QSettings, QSize, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QRadioButton, QScrollArea,
    QSizePolicy, QSpacerItem, QStackedWidget, QTableWidget, QTableWidgetItem,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import __version__
from ..ingest import SUPPORTED, load_many
from ..metrics.engine import load_matrix
from .blocker_taxonomy import group_blockers
from .theme import FONT_MONO, FONT_SANS, apply_theme, system_theme
from .widgets import (CategoryBar, EmptyState, FigureCard, ScoreGauge, Sparkline,
                      StatusPill, icon, open_local)


APP_NAME = "ScheduleIQ"
ORG_NAME = "Long International"
ASSET_DIR = Path(__file__).with_name("assets")
ICON_PATH = ASSET_DIR / "scheduleiq_icon.svg"

STATUS_TONE = {
    "PASS": "success", "FAIL": "danger", "WARNING": "warning",
    "INFO": "info", "N/A": "muted", "NOT EVALUATED": "muted",
}
STATUS_BG = {
    "PASS": "#E7F5F0", "FAIL": "#FCEBEC", "WARNING": "#FFF4DC",
    "INFO": "#EAF2F8", "N/A": "#EDF1F2", "NOT EVALUATED": "#EDF1F2",
}
STATUS_FG = {
    "PASS": "#23856D", "FAIL": "#B23D45", "WARNING": "#9A6515",
    "INFO": "#3979A8", "N/A": "#65747A", "NOT EVALUATED": "#65747A",
}


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child is not None:
            _clear_layout(child)


def _card(parent=None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame(parent)
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(20, 18, 20, 18)
    lay.setSpacing(12)
    return frame, lay


def _page(title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setContentsMargins(28, 16, 28, 24)
    lay.setSpacing(16)
    title_label = QLabel(title)
    title_label.setObjectName("pageTitle")
    lay.addWidget(title_label)
    sub = QLabel(subtitle)
    sub.setObjectName("pageSubtitle")
    sub.setWordWrap(True)
    lay.addWidget(sub)
    return page, lay


class RunWorker(QThread):
    progressed = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, paths, out_dir, overrides, paper, make_pdf, benchmark,
                 events_csv=None, responsibility_csv=None, no_cockpit=False,
                 internal_workbook=False):
        super().__init__()
        self.paths, self.out_dir = paths, out_dir
        self.overrides, self.paper = overrides, paper
        self.make_pdf, self.benchmark = make_pdf, benchmark
        self.events_csv = events_csv
        self.responsibility_csv = responsibility_csv
        self.no_cockpit = no_cockpit
        self.internal_workbook = internal_workbook

    def run(self):
        profile = None
        try:
            from ..runner import run
            if self.overrides:
                with tempfile.NamedTemporaryFile("w", suffix=".json",
                                                 delete=False) as tf:
                    json.dump(self.overrides, tf)
                    profile = tf.name
            rr = run(
                self.paths, self.out_dir, profile=profile, paper=self.paper,
                make_pdf=self.make_pdf, benchmark=self.benchmark,
                events_csv=self.events_csv or None,
                responsibility_csv=self.responsibility_csv or None,
                no_cockpit=self.no_cockpit,
                internal_workbook=self.internal_workbook,
                progress=self.progressed.emit,
            )
            self.finished_ok.emit(rr)
        except Exception:
            self.failed.emit(traceback.format_exc())
        finally:
            if profile:
                try:
                    os.unlink(profile)
                except OSError:
                    pass


class ThresholdDialog(QDialog):
    """Searchable threshold editor: published defaults plus run overrides."""

    def __init__(self, overrides: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Threshold profile")
        self.resize(980, 650)
        self.overrides = dict(overrides)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        title = QLabel("Published defaults and analyst overrides")
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        note = QLabel(
            "Enter only the values you intend to override. Every override is "
            "identified in the generated reports and workbooks; blank values "
            "retain the governed standard default.")
        note.setObjectName("pageSubtitle")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search check ID or name…")
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        self.table = QTableWidget()
        matrix = load_matrix()
        rows = [c for c in matrix if c.threshold is not None]
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Check", "Unit", "Standard default", "Override"])
        self.table.setRowCount(len(rows))
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        for i, check in enumerate(rows):
            for j, value in enumerate((check.id, check.name, check.unit,
                                       f"{check.threshold:g}")):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(i, j, item)
            override = self.overrides.get(check.id)
            self.table.setItem(i, 4, QTableWidgetItem(
                "" if override is None else f"{override:g}"))
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        lay.addWidget(self.table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _filter(self, text: str):
        text = text.strip().lower()
        for row in range(self.table.rowCount()):
            haystack = " ".join(
                self.table.item(row, col).text() for col in (0, 1, 2)
                if self.table.item(row, col))
            self.table.setRowHidden(row, text not in haystack.lower())

    def result_overrides(self) -> dict:
        out = {}
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 4)
            text = (item.text() if item else "").strip()
            if text:
                try:
                    out[self.table.item(row, 0).text()] = float(text)
                except ValueError:
                    continue
        return out


class MatrixDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Metric & Heuristic Matrix")
        self.resize(1080, 680)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 20)
        title = QLabel("Metric & Heuristic Matrix")
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        rows = load_matrix()
        note = QLabel(
            f"{len(rows)} governed checks. Definitions, populations, thresholds, "
            "and references are read directly from the packaged matrix.yaml.")
        note.setObjectName("pageSubtitle")
        lay.addWidget(note)
        table = QTableWidget(len(rows), 5)
        table.setHorizontalHeaderLabels(
            ["ID", "Category", "Check", "Default", "Reference"])
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        for r, check in enumerate(rows):
            default = "Informational" if check.threshold is None else (
                f"≤ {check.threshold:g}" if check.direction == "max"
                else f"≥ {check.threshold:g}")
            values = (check.id, check.category, check.name, default,
                      "; ".join(check.references))
            for c, value in enumerate(values):
                table.setItem(r, c, QTableWidgetItem(value))
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        lay.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        lay.addWidget(buttons)


class MainWindow(QMainWindow):
    NAV = (
        ("files", "▤", "Files"),
        ("report", "◉", "Report Card"),
        ("checks", "✓", "Checks"),
        ("trends", "↗", "Trends"),
        ("paths", "⌁", "Paths"),
        ("forensics", "◇", "Forensics"),
        ("settings", "⚙", "Settings"),
    )

    def __init__(self):
        super().__init__()
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.overrides: dict = {}
        self.out_dir = self.settings.value(
            "outputFolder", os.path.join(os.path.expanduser("~"),
                                         "ScheduleIQ Output"))
        self.current_result = None
        self.current_card = None
        self._result_sets: list[tuple[str, list]] = []
        self._theme_name = self.settings.value(
            "theme", system_theme(QApplication.instance()))
        self.setWindowTitle(
            f"ScheduleIQ v{__version__} — Schedule Intelligence")
        self.setMinimumSize(1120, 720)
        self.resize(1480, 920)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self._build_shell()
        self._build_menu()
        self.setAcceptDrops(True)
        self.set_theme(self._theme_name)
        self.navigate("files")

    # ---------------------------------------------------------------- shell
    def _build_shell(self):
        root = QWidget()
        root.setObjectName("appCanvas")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(236)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 22, 18, 18)
        side.setSpacing(5)
        brand = QHBoxLayout()
        mark = QLabel("SI")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(40, 40)
        mark.setStyleSheet(
            "background:#2FB0C2; color:white; border-radius:11px; "
            "font-size:16px; font-weight:600; letter-spacing:0.5px;")
        brand.addWidget(mark)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        name = QLabel("ScheduleIQ")
        name.setObjectName("brandMark")
        brand_text.addWidget(name)
        sub = QLabel("SCHEDULE INTELLIGENCE")
        sub.setObjectName("brandSub")
        brand_text.addWidget(sub)
        brand.addLayout(brand_text)
        side.addLayout(brand)
        side.addSpacing(24)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = {}
        self.page_indexes = {}
        for key, _glyph, label in self.NAV:
            button = QPushButton(f"   {label}")
            button.setObjectName("navButton")
            button.setIcon(icon(key, 20))
            button.setIconSize(QSize(20, 20))
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, k=key: self.navigate(k))
            self.nav_group.addButton(button)
            self.nav_buttons[key] = button
            side.addWidget(button)
        side.addStretch()
        state = QFrame()
        state.setObjectName("statusCard")
        state_lay = QVBoxLayout(state)
        state_lay.setContentsMargins(14, 12, 14, 13)
        state_lay.setSpacing(7)
        state_row = QHBoxLayout()
        state_row.setSpacing(9)
        self.status_dot = QFrame()
        self.status_dot.setFixedSize(8, 8)
        state_row.addWidget(self.status_dot, 0, Qt.AlignVCenter)
        self.sidebar_state = QLabel("READY")
        self.sidebar_state.setObjectName("statusLabel")
        state_row.addWidget(self.sidebar_state)
        state_row.addStretch()
        state_lay.addLayout(state_row)
        self.sidebar_detail = QLabel("Add schedule files to begin")
        self.sidebar_detail.setObjectName("statusDetail")
        self.sidebar_detail.setWordWrap(True)
        state_lay.addWidget(self.sidebar_detail)
        side.addWidget(state)
        self._set_status("READY", "Add schedule files to begin", "ready")
        version = QLabel(f"v{__version__}")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("color:#739097; font-size:10px; padding-top:8px;")
        side.addWidget(version)
        root_layout.addWidget(sidebar)

        workspace = QWidget()
        work = QVBoxLayout(workspace)
        work.setContentsMargins(0, 0, 0, 0)
        work.setSpacing(0)
        top = QFrame()
        top.setObjectName("topBar")
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(28, 14, 28, 10)
        self.context_label = QLabel("Workspace  /  Files")
        self.context_label.setObjectName("muted")
        top_lay.addWidget(self.context_label)
        top_lay.addStretch()
        self.open_btn = QPushButton("Open output")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self.open_output)
        top_lay.addWidget(self.open_btn)
        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("themeButton")
        self.theme_btn.setToolTip("Switch between light and dark theme")
        self.theme_btn.setIconSize(QSize(18, 18))
        self.theme_btn.clicked.connect(self.toggle_theme)
        top_lay.addWidget(self.theme_btn)
        self.run_btn = QPushButton("Run analysis")
        self.run_btn.setObjectName("primaryButton")
        self.run_btn.clicked.connect(self.run_analysis)
        top_lay.addWidget(self.run_btn)
        work.addWidget(top)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        work.addWidget(self.progress)

        self.stack = QStackedWidget()
        self.pages = {
            "files": self._build_files_page(),
            "report": self._build_report_page(),
            "checks": self._build_checks_page(),
            "trends": self._build_trends_page(),
            "paths": self._build_paths_page(),
            "forensics": self._build_forensics_page(),
            "settings": self._build_settings_page(),
        }
        for index, (key, page) in enumerate(self.pages.items()):
            self.stack.addWidget(page)
            self.page_indexes[key] = index
        work.addWidget(self.stack, 1)
        self.status_bar = QLabel("Ready — analysis runs locally on this computer.")
        self.status_bar.setObjectName("muted")
        self.status_bar.setContentsMargins(28, 8, 28, 10)
        work.addWidget(self.status_bar)
        self.status_label = self.status_bar  # compatibility with the prior GUI
        root_layout.addWidget(workspace, 1)

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("&File")
        add_action = QAction("Add schedule files…", self)
        add_action.setShortcut(QKeySequence.Open)
        add_action.triggered.connect(self.add_files)
        file_menu.addAction(add_action)
        run_action = QAction("Run analysis", self)
        run_action.setShortcut(QKeySequence("Ctrl+Return"))
        run_action.triggered.connect(self.run_analysis)
        file_menu.addAction(run_action)
        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        view_menu = self.menuBar().addMenu("&View")
        theme_action = QAction("Toggle light / dark theme", self)
        theme_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
        theme_action.triggered.connect(self.toggle_theme)
        view_menu.addAction(theme_action)
        help_menu = self.menuBar().addMenu("&Help")
        matrix_action = QAction("Metric & Heuristic Matrix", self)
        matrix_action.triggered.connect(lambda: MatrixDialog(self).exec())
        help_menu.addAction(matrix_action)
        about_action = QAction("About ScheduleIQ", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    # ---------------------------------------------------------------- pages
    def _build_files_page(self):
        page, lay = _page(
            "Schedule files",
            "Build a defensible series or benchmark set. Files are pre-read, "
            "ordered by data date, and checked for ordering warnings before run.")
        content = QHBoxLayout()
        content.setSpacing(16)
        file_card, fl = _card()
        file_card.setObjectName("dropCard")
        self.drop_card = file_card
        head = QHBoxLayout()
        title = QLabel("Analysis set")
        title.setObjectName("sectionTitle")
        head.addWidget(title)
        head.addStretch()
        self.file_count = QLabel("0 FILES")
        self.file_count.setObjectName("muted")
        head.addWidget(self.file_count)
        fl.addLayout(head)
        drop_hint = QLabel("Drop .xer, .xml, or .mpp files anywhere in this window")
        drop_hint.setObjectName("muted")
        fl.addWidget(drop_hint)
        self.file_list = QListWidget()
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.file_list.setMinimumHeight(320)
        fl.addWidget(self.file_list, 1)
        buttons = QHBoxLayout()
        add_btn = QPushButton("Add files")
        add_btn.setObjectName("primaryButton")
        add_btn.setIcon(icon("plus", 16, "white"))
        add_btn.setIconSize(QSize(16, 16))
        add_btn.clicked.connect(self.add_files)
        buttons.addWidget(add_btn)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self.remove_selected)
        buttons.addWidget(remove_btn)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_files)
        buttons.addWidget(clear_btn)
        buttons.addStretch()
        fl.addLayout(buttons)
        self.warn_label = QLabel("")
        self.warn_label.setObjectName("warningText")
        self.warn_label.setWordWrap(True)
        fl.addWidget(self.warn_label)
        content.addWidget(file_card, 3)

        right = QVBoxLayout()
        mode_card, ml = _card()
        mode_title = QLabel("Analysis mode")
        mode_title.setObjectName("sectionTitle")
        ml.addWidget(mode_title)
        self.mode_series = QRadioButton("Series")
        self.mode_series.setChecked(True)
        ml.addWidget(self.mode_series)
        series_note = QLabel("Ordered updates of one project — trend and change analysis")
        series_note.setObjectName("muted")
        series_note.setWordWrap(True)
        ml.addWidget(series_note)
        self.mode_bench = QRadioButton("Benchmark")
        ml.addWidget(self.mode_bench)
        bench_note = QLabel("Separate projects — side-by-side comparison")
        bench_note.setObjectName("muted")
        bench_note.setWordWrap(True)
        ml.addWidget(bench_note)
        right.addWidget(mode_card)
        ready_card, rl = _card()
        rt = QLabel("Run readiness")
        rt.setObjectName("sectionTitle")
        rl.addWidget(rt)
        self.readiness = QLabel("Waiting for files")
        self.readiness.setObjectName("statusHeadline")
        rl.addWidget(self.readiness)
        self.readiness_detail = QLabel(
            "Add at least one supported schedule. Three or more updates produce "
            "the richest trend and reliability views.")
        self.readiness_detail.setObjectName("muted")
        self.readiness_detail.setWordWrap(True)
        rl.addWidget(self.readiness_detail)
        right.addWidget(ready_card)
        right.addStretch()
        content.addLayout(right, 2)
        lay.addLayout(content, 1)
        return page

    def _build_report_page(self):
        page, lay = _page(
            "Report Card",
            "A concise view of schedule health, governed category scores, gates, "
            "and movement across the update series.")
        body = QScrollArea()
        body.setWidgetResizable(True)
        # Width-responsive dashboard; it only scrolls vertically. Suppress the
        # spurious horizontal bar Qt shows when the vertical scrollbar's width
        # reservation nudges the canvas minimum past the viewport.
        body.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        canvas = QWidget()
        self.report_layout = QVBoxLayout(canvas)
        self.report_layout.setContentsMargins(0, 0, 4, 4)
        self.report_layout.setSpacing(16)
        hero = QHBoxLayout()
        score_card, score_lay = _card()
        score_lay.setAlignment(Qt.AlignCenter)
        self.gauge = ScoreGauge()
        score_lay.addWidget(self.gauge, 0, Qt.AlignCenter)
        self.score_caption = QLabel("No analysis yet")
        self.score_caption.setObjectName("muted")
        self.score_caption.setAlignment(Qt.AlignCenter)
        score_lay.addWidget(self.score_caption)
        hero.addWidget(score_card, 2)

        summary_card, summary = _card()
        row = QHBoxLayout()
        title = QLabel("Latest update")
        title.setObjectName("sectionTitle")
        row.addWidget(title)
        row.addStretch()
        self.coverage_pill = StatusPill("NO DATA", "muted")
        row.addWidget(self.coverage_pill)
        summary.addLayout(row)
        self.report_label = QLabel("—")
        self.report_label.setObjectName("metricValue")
        summary.addWidget(self.report_label)
        self.badges = QHBoxLayout()
        for status in ("FAIL", "WARNING", "PASS", "N/A"):
            pill = StatusPill(f"0 {status}", STATUS_TONE[status])
            pill.setProperty("statusKey", status)
            self.badges.addWidget(pill)
        self.badges.addStretch()
        summary.addLayout(self.badges)
        self.gate_note = QLabel("Run an analysis to populate the governed card.")
        self.gate_note.setObjectName("muted")
        self.gate_note.setWordWrap(True)
        summary.addWidget(self.gate_note)
        hero.addWidget(summary_card, 3)
        self.report_layout.addLayout(hero)

        lower = QHBoxLayout()
        category_card, cat_lay = _card()
        cat_title = QLabel("Category performance")
        cat_title.setObjectName("sectionTitle")
        cat_lay.addWidget(cat_title)
        self.category_layout = QVBoxLayout()
        self.category_layout.setSpacing(8)
        cat_lay.addLayout(self.category_layout)
        cat_lay.addStretch()
        lower.addWidget(category_card, 3)
        trend_card, trend_lay = _card()
        trend_title = QLabel("Score trajectory")
        trend_title.setObjectName("sectionTitle")
        trend_lay.addWidget(trend_title)
        self.report_sparkline = Sparkline()
        trend_lay.addWidget(self.report_sparkline, 1)
        self.trend_caption = QLabel("Per-update score movement")
        self.trend_caption.setObjectName("muted")
        trend_lay.addWidget(self.trend_caption)
        lower.addWidget(trend_card, 4)
        self.report_layout.addLayout(lower)

        factor_card, factor_lay = _card()
        factor_title = QLabel("Primary score drivers")
        factor_title.setObjectName("sectionTitle")
        factor_lay.addWidget(factor_title)
        self.factor_layout = QVBoxLayout()
        placeholder = QLabel("Top factors will appear after analysis.")
        placeholder.setObjectName("muted")
        self.factor_layout.addWidget(placeholder)
        factor_lay.addLayout(self.factor_layout)
        self.report_layout.addWidget(factor_card)
        self.report_layout.addStretch()
        body.setWidget(canvas)
        lay.addWidget(body, 1)
        return page

    def _build_checks_page(self):
        page, lay = _page(
            "Checks",
            "Search, sort, and filter governed results. Expand a check to inspect "
            "the activities, relationships, calendars, or fields behind it.")
        filters = QHBoxLayout()
        self.check_search = QLineEdit()
        self.check_search.setPlaceholderText("Search checks, findings, IDs, or narrative…")
        self.check_search.textChanged.connect(self.filter_checks)
        filters.addWidget(self.check_search, 3)
        self.check_source = QComboBox()
        self.check_source.addItem("Latest update")
        self.check_source.currentIndexChanged.connect(self.populate_checks)
        filters.addWidget(self.check_source, 1)
        self.check_status = QComboBox()
        self.check_status.addItems(
            ["All statuses", "FAIL", "WARNING", "PASS", "INFO", "NOT EVALUATED", "N/A"])
        self.check_status.currentTextChanged.connect(self.filter_checks)
        filters.addWidget(self.check_status, 1)
        lay.addLayout(filters)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Check / finding", "Value", "Threshold", "Status", "Result"])
        self.tree.headerItem().setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
        self.tree.headerItem().setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.AscendingOrder)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(4, QHeaderView.Stretch)
        lay.addWidget(self.tree, 1)
        return page

    def _build_trends_page(self):
        page, lay = _page(
            "Trends",
            "Follow health, card grades, and exception counts across ordered updates.")
        top = QHBoxLayout()
        trend_card, tl = _card()
        title = QLabel("Health trajectory")
        title.setObjectName("sectionTitle")
        tl.addWidget(title)
        self.health_sparkline = Sparkline()
        tl.addWidget(self.health_sparkline, 1)
        top.addWidget(trend_card, 3)
        movement_card, ml = _card()
        mtitle = QLabel("Latest movement")
        mtitle.setObjectName("sectionTitle")
        ml.addWidget(mtitle)
        self.movement_value = QLabel("—")
        self.movement_value.setObjectName("statusHeadline")
        ml.addWidget(self.movement_value)
        self.movement_note = QLabel("Awaiting an update series")
        self.movement_note.setObjectName("muted")
        self.movement_note.setWordWrap(True)
        ml.addWidget(self.movement_note)
        ml.addStretch()
        top.addWidget(movement_card, 1)
        lay.addLayout(top, 2)
        self.trend_table = QTableWidget(0, 6)
        self.trend_table.setHorizontalHeaderLabels(
            ["Update", "Data date", "Health", "Card grade", "Fails", "Warnings"])
        for col, al in ((1, Qt.AlignCenter), (2, Qt.AlignRight | Qt.AlignVCenter),
                        (3, Qt.AlignCenter), (4, Qt.AlignRight | Qt.AlignVCenter),
                        (5, Qt.AlignRight | Qt.AlignVCenter)):
            self.trend_table.horizontalHeaderItem(col).setTextAlignment(al)
        self.trend_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.trend_table.setAlternatingRowColors(True)
        self.trend_table.verticalHeader().setVisible(False)
        self.trend_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 6):
            self.trend_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeToContents)
        lay.addWidget(self.trend_table, 3)
        return page

    def _gallery_page(self, title: str, subtitle: str):
        page, lay = _page(title, subtitle)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        canvas = QWidget()
        grid = QGridLayout(canvas)
        grid.setContentsMargins(0, 0, 4, 4)
        grid.setSpacing(16)
        scroll.setWidget(canvas)
        lay.addWidget(scroll, 1)
        return page, grid

    def _build_paths_page(self):
        page, self.paths_grid = self._gallery_page(
            "Paths",
            "Path diagnostics, milestone impact visuals, and the interactive "
            "network cockpit generated by the existing analysis pipeline.")
        empty = EmptyState(
            "No path visuals yet",
            "Run an analysis to generate the milestone-impact and as-built path views.",
            "Go to files", glyph="paths")
        empty.action_requested.connect(lambda: self.navigate("files"))
        self.paths_grid.addWidget(empty, 0, 0, 1, 2)
        return page

    def _build_forensics_page(self):
        page, self.forensics_grid = self._gallery_page(
            "Forensics",
            "Half-step, daily ledger, robustness, and schedule-risk diagnostics. "
            "These are analytical exhibits, not causation or entitlement opinions.")
        empty = EmptyState(
            "No forensic visuals yet",
            "Run two or more engine-consistent updates to populate forensic exhibits.",
            "Go to files", glyph="forensics")
        empty.action_requested.connect(lambda: self.navigate("files"))
        self.forensics_grid.addWidget(empty, 0, 0, 1, 2)
        return page

    def _build_settings_page(self):
        page, lay = _page(
            "Settings",
            "Control output format and optional overlays. Standard defaults remain "
            "governed; per-run overrides are always disclosed in outputs.")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        # This panel is a width-responsive form (stretched 2-column grid,
        # wrapping copy); it only ever scrolls vertically. Suppress the spurious
        # horizontal bar that Qt otherwise shows when the vertical scrollbar's
        # width reservation nudges the canvas minimum past the viewport.
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        canvas = QWidget()
        grid = QGridLayout(canvas)
        grid.setContentsMargins(0, 0, 4, 4)
        grid.setSpacing(16)

        output_card, output = _card()
        ot = QLabel("Report output")
        ot.setObjectName("sectionTitle")
        output.addWidget(ot)
        output.addWidget(QLabel("Paper size"))
        self.paper = QComboBox()
        self.paper.addItems(["letter", "a4"])
        output.addWidget(self.paper)
        self.pdf_cb = QCheckBox("Create PDF via Microsoft Word")
        self.pdf_cb.setChecked(True)
        output.addWidget(self.pdf_cb)
        self.cockpit_cb = QCheckBox("Generate interactive network cockpit")
        self.cockpit_cb.setChecked(True)
        output.addWidget(self.cockpit_cb)
        out_label = QLabel("Output folder")
        output.addWidget(out_label)
        out_row = QHBoxLayout()
        self.out_path = QLineEdit(self.out_dir)
        self.out_path.setReadOnly(True)
        out_row.addWidget(self.out_path, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.pick_out_dir)
        out_row.addWidget(browse)
        output.addLayout(out_row)
        grid.addWidget(output_card, 0, 0)

        overlays_card, overlays = _card()
        evt = QLabel("Evidence overlays")
        evt.setObjectName("sectionTitle")
        overlays.addWidget(evt)
        overlays.addWidget(QLabel("Delay-events CSV (--events)"))
        erow = QHBoxLayout()
        self.events_path = QLineEdit()
        self.events_path.setPlaceholderText("Optional event register")
        erow.addWidget(self.events_path, 1)
        eb = QPushButton("Choose…")
        eb.clicked.connect(lambda: self._pick_csv(self.events_path, "Delay-events CSV"))
        erow.addWidget(eb)
        overlays.addLayout(erow)
        overlays.addWidget(QLabel("Responsibility CSV (--responsibility)"))
        rrow = QHBoxLayout()
        self.responsibility_path = QLineEdit()
        self.responsibility_path.setPlaceholderText("Optional responsibility mapping")
        rrow.addWidget(self.responsibility_path, 1)
        rb = QPushButton("Choose…")
        rb.clicked.connect(lambda: self._pick_csv(
            self.responsibility_path, "Responsibility CSV"))
        rrow.addWidget(rb)
        overlays.addLayout(rrow)
        overlays.addStretch()
        grid.addWidget(overlays_card, 0, 1)

        governance_card, governance = _card()
        gt = QLabel("Governance and thresholds")
        gt.setObjectName("sectionTitle")
        governance.addWidget(gt)
        gn = QLabel(
            "The matrix defaults are the published standard. Analyst overrides "
            "apply only to this run and are stamped into every output.")
        gn.setObjectName("muted")
        gn.setWordWrap(True)
        governance.addWidget(gn)
        self.override_summary = QLabel("Standard defaults — no overrides")
        governance.addWidget(self.override_summary)
        threshold = QPushButton("Edit threshold profile…")
        threshold.clicked.connect(self.edit_thresholds)
        governance.addWidget(threshold)
        matrix = QPushButton("View Metric && Heuristic Matrix")
        matrix.clicked.connect(lambda: MatrixDialog(self).exec())
        governance.addWidget(matrix)
        governance.addStretch()
        grid.addWidget(governance_card, 1, 0)

        privileged_card, privileged = _card()
        pt = QLabel("Internal Proprietary Metrics")
        pt.setObjectName("sectionTitle")
        privileged.addWidget(pt)
        self.internal_cb = QCheckBox(
            "Include internal proprietary Long International forensic metrics "
            "(LI-11–LI-15)")
        privileged.addWidget(self.internal_cb)
        warning = QLabel(
            "NOT FOR DISSEMINATION. Internal proprietary Long International "
            "forensic work product — not for a counterparty and excluded from the "
            "standard artifact set. WEIGHT-0: does not alter the standard Report "
            "Card grade.")
        warning.setObjectName("privilegedWarning")
        warning.setWordWrap(True)
        privileged.addWidget(warning)
        privileged.addStretch()
        grid.addWidget(privileged_card, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        scroll.setWidget(canvas)
        lay.addWidget(scroll, 1)
        return page

    # ------------------------------------------------------------- navigation
    def navigate(self, key: str):
        if key not in self.page_indexes:
            return
        self.stack.setCurrentIndex(self.page_indexes[key])
        self.nav_buttons[key].setChecked(True)
        label = next(label for k, _, label in self.NAV if k == key)
        self.context_label.setText(f"Workspace  /  {label}")

    def set_theme(self, name: str):
        self._theme_name = "dark" if name == "dark" else "light"
        apply_theme(QApplication.instance(), self._theme_name)
        self.settings.setValue("theme", self._theme_name)
        dark = self._theme_name == "dark"
        self.theme_btn.setIcon(icon("sun" if dark else "moon", 18,
                                    "#E6EEF2" if dark else "#16242A"))
        for widget in (self.gauge, self.report_sparkline, self.health_sparkline):
            widget.update()
        for i in range(self.category_layout.count()):
            widget = self.category_layout.itemAt(i).widget()
            if widget:
                widget.update()

    def toggle_theme(self):
        self.set_theme("light" if self._theme_name == "dark" else "dark")

    # Sidebar status tones (on the always-dark sidebar, so fixed light-on-dark).
    _STATUS_TONES = {
        "ready": "#5FD0BE", "analyzing": "#E6B45C",
        "complete": "#5FD0BE", "failed": "#F08A8A",
    }

    def _set_status(self, state: str, detail: str, tone: str):
        """Update the sidebar status card — dot colour, label, and detail."""
        color = self._STATUS_TONES.get(tone, self._STATUS_TONES["ready"])
        self.status_dot.setStyleSheet(f"background:{color}; border-radius:4px;")
        self.sidebar_state.setText(state)
        self.sidebar_state.setStyleSheet(f"color:{color};")
        self.sidebar_detail.setText(detail)

    # ---------------------------------------------------------------- files
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.drop_card.setProperty("dragActive", True)
            self.drop_card.style().unpolish(self.drop_card)
            self.drop_card.style().polish(self.drop_card)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.drop_card.setProperty("dragActive", False)
        self.drop_card.style().unpolish(self.drop_card)
        self.drop_card.style().polish(self.drop_card)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.drop_card.setProperty("dragActive", False)
        self.drop_card.style().unpolish(self.drop_card)
        self.drop_card.style().polish(self.drop_card)
        self._add_paths([url.toLocalFile() for url in event.mimeData().urls()])
        event.acceptProposedAction()

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add schedule files", "",
            "Schedules (*.xer *.xml *.mpp);;All files (*)")
        self._add_paths(paths)

    def _add_paths(self, paths):
        existing = {self.file_list.item(i).data(Qt.UserRole)
                    for i in range(self.file_list.count())}
        for path in paths:
            path = os.path.abspath(path) if path else ""
            if path and os.path.splitext(path)[1].lower() in SUPPORTED \
                    and path not in existing:
                item = QListWidgetItem(os.path.basename(path))
                item.setData(Qt.UserRole, path)
                item.setToolTip(path)
                self.file_list.addItem(item)
                existing.add(path)
        self._refresh_order()

    def remove_selected(self):
        for item in self.file_list.selectedItems():
            self.file_list.takeItem(self.file_list.row(item))
        self._refresh_order()

    def clear_files(self):
        self.file_list.clear()
        self._refresh_order()

    def _refresh_order(self):
        paths = [self.file_list.item(i).data(Qt.UserRole)
                 for i in range(self.file_list.count())]
        count = len(paths)
        self.file_count.setText(f"{count} FILE{'S' if count != 1 else ''}")
        if not paths:
            self.warn_label.clear()
            self.readiness.setText("Waiting for files")
            self.readiness_detail.setText(
                "Add at least one supported schedule. Three or more updates "
                "produce the richest trend and reliability views.")
            self._set_status("READY", "Add schedule files to begin", "ready")
            return
        try:
            from ..trend.series import order_and_validate
            schedules = load_many(paths)
            ordered, warnings = order_and_validate(schedules)
            by_source = {}
            for path in paths:
                by_source.setdefault(os.path.basename(path), []).append(path)
            self.file_list.clear()
            for schedule in ordered:
                candidates = by_source.get(schedule.source_file, [])
                path = candidates.pop(0) if candidates else next(
                    (p for p in paths if os.path.basename(p) == schedule.source_file),
                    schedule.source_file)
                item = QListWidgetItem(f"{schedule.source_file}   ·   {schedule.label()}")
                item.setData(Qt.UserRole, path)
                item.setToolTip(path)
                self.file_list.addItem(item)
            if warnings:
                self.warn_label.setText("\n".join(w.message for w in warnings))
                self.readiness.setText("Review warnings")
                self.readiness_detail.setText(
                    "The set is ordered, but the series warnings should be "
                    "confirmed before analysis.")
            else:
                self.warn_label.setText(
                    "Files ordered by data date — confirm Series or Benchmark mode."
                    if len(ordered) > 1 else "Ready to analyze.")
                self.readiness.setText("Ready to run")
                self.readiness_detail.setText(
                    f"{len(ordered)} schedule file{'s' if len(ordered) != 1 else ''} "
                    "successfully pre-read and ordered.")
            self._set_status("READY", f"{len(ordered)} file(s) ready", "ready")
        except Exception as exc:
            self.warn_label.setText(f"Could not pre-read a file: {exc}")
            self.readiness.setText("Input needs attention")

    # -------------------------------------------------------------- settings
    def edit_thresholds(self):
        dialog = ThresholdDialog(self.overrides, self)
        if dialog.exec():
            self.overrides = dialog.result_overrides()
            text = (f"{len(self.overrides)} analyst override(s) active"
                    if self.overrides else "Standard defaults — no overrides")
            self.override_summary.setText(text)
            self.status_bar.setText(text)

    def pick_out_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Output folder", self.out_dir)
        if directory:
            self.out_dir = directory
            self.out_path.setText(directory)
            self.settings.setValue("outputFolder", directory)
            self.status_bar.setText(f"Output folder: {directory}")

    def _pick_csv(self, field: QLineEdit, title: str):
        path, _ = QFileDialog.getOpenFileName(
            self, title, "", "CSV files (*.csv);;All files (*)")
        if path:
            field.setText(path)

    # ------------------------------------------------------------------ run
    def run_analysis(self):
        paths = [self.file_list.item(i).data(Qt.UserRole)
                 for i in range(self.file_list.count())]
        if not paths:
            QMessageBox.warning(self, APP_NAME, "Add at least one schedule file.")
            self.navigate("files")
            return
        self.run_btn.setEnabled(False)
        self.run_btn.setText("Analyzing…")
        self.progress.show()
        self._set_status("ANALYZING", "Preparing local analysis", "analyzing")
        self.status_bar.setText("Starting analysis…")
        self.worker = RunWorker(
            paths, self.out_dir, self.overrides, self.paper.currentText(),
            self.pdf_cb.isChecked(), self.mode_bench.isChecked(),
            self.events_path.text().strip(),
            self.responsibility_path.text().strip(),
            not self.cockpit_cb.isChecked(), self.internal_cb.isChecked())
        self.worker.progressed.connect(self._on_progress)
        self.worker.finished_ok.connect(self.show_results)
        self.worker.failed.connect(self.show_error)
        self.worker.start()

    def _on_progress(self, text: str):
        self.status_bar.setText(text)
        self.sidebar_detail.setText(text[:54])

    def show_error(self, trace: str):
        self.progress.hide()
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Run analysis")
        self._set_status("RUN FAILED", "See error details", "failed")
        QMessageBox.critical(self, "ScheduleIQ — run failed", trace[-4000:])

    def show_results(self, result):
        self.current_result = result
        self.progress.hide()
        self.run_btn.setEnabled(True)
        self.run_btn.setText("Run analysis")
        self.open_btn.setEnabled(True)
        self._set_status("ANALYSIS COMPLETE", "Report ready", "complete")
        try:
            from ..scorecard import score_series
            self.current_card = score_series(result.analysis)
        except Exception as exc:  # defensive: dashboard never sinks a run
            self.current_card = None
            result.messages.append(f"GUI report card view skipped: {exc}")
        self._populate_report()
        self._populate_result_sets()
        self._populate_trends()
        self._populate_galleries()
        latest = result.analysis.assessments[-1]
        self.sidebar_detail.setText(
            f"{latest.health_score:.0f}/100 health · "
            f"{latest.counts.get('FAIL', 0)} fail")
        note = (" ".join(result.messages)[:420] if result.messages else
                "Outputs generated successfully.")
        self.status_bar.setText(
            f"Done · health {latest.health_score:.0f}/100 · "
            f"{latest.counts.get('FAIL', 0)} fail · "
            f"{latest.counts.get('WARNING', 0)} warning. {note}")
        self.navigate("report")

    def _populate_report(self):
        analysis = self.current_result.analysis
        latest = analysis.assessments[-1]
        card = self.current_card
        if card is None:
            self.gauge.set_score(latest.health_score, "—")
            self.report_label.setText(analysis.schedules[-1].label())
            return
        display_card = card
        categories = getattr(card, "series_categories", [])
        if not categories and getattr(card, "file_cards", None):
            display_card = card.file_cards[-1]
            categories = display_card.categories
        self.gauge.set_score(display_card.overall, display_card.letter)
        self.score_caption.setText(
            f"{display_card.profile.title()} profile · {display_card.coverage_graded}/"
            f"{display_card.coverage_total} graded"
            if hasattr(display_card, "profile") else
            f"Series card · {display_card.coverage_graded}/"
            f"{display_card.coverage_total} graded")
        self.report_label.setText(analysis.schedules[-1].label())
        self.coverage_pill.setText(
            f"{display_card.coverage_graded}/{display_card.coverage_total} GRADED")
        counts = latest.counts
        for i in range(self.badges.count()):
            widget = self.badges.itemAt(i).widget()
            if widget and widget.property("statusKey"):
                status = widget.property("statusKey")
                widget.setText(f"{counts.get(status, 0)} {status}")
        gates = getattr(display_card, "gates", [])
        self.gate_note.setText(
            "Active gates: " + ", ".join(gate.name for gate in gates)
            if gates else "No Report Card gates tripped on this view.")
        _clear_layout(self.category_layout)
        for category in categories:
            self.category_layout.addWidget(CategoryBar(category.name, category.score))
        if not categories:
            self.category_layout.addWidget(CategoryBar("No gradeable categories", None))
        file_cards = list(getattr(card, "file_cards", []))
        self.report_sparkline.set_values(
            [fc.overall for fc in file_cards],
            [fc.schedule_label for fc in file_cards])
        trajectory = getattr(card, "trajectory", None)
        if trajectory and trajectory.slope is not None:
            direction = "improving" if trajectory.slope > 0 else (
                "declining" if trajectory.slope < 0 else "stable")
            self.trend_caption.setText(
                f"Trajectory {direction} · slope {trajectory.slope:+.2f} points/update")
        else:
            self.trend_caption.setText("Per-update Report Card score")
        _clear_layout(self.factor_layout)
        factors = list(getattr(display_card, "top_factors", []))[:5]
        if not factors:
            empty = QLabel("No graded score drivers are available for this view.")
            empty.setObjectName("muted")
            self.factor_layout.addWidget(empty)
        for points, check_id, offenders in factors:
            row = QHBoxLayout()
            ident = QLabel(check_id)
            ident.setStyleSheet("font-weight:700;")
            row.addWidget(ident)
            row.addWidget(QLabel(f"{offenders} finding(s)"))
            row.addStretch()
            row.addWidget(StatusPill(f"−{points:.1f} pts", "danger"))
            self.factor_layout.addLayout(row)

    def _populate_result_sets(self):
        analysis = self.current_result.analysis
        self._result_sets = [
            (schedule.label(), assessment.results)
            for schedule, assessment in zip(analysis.schedules, analysis.assessments)]
        if analysis.series_results:
            self._result_sets.append(("Series metrics", analysis.series_results))
        self.check_source.blockSignals(True)
        self.check_source.clear()
        for label, _ in self._result_sets:
            self.check_source.addItem(label)
        self.check_source.setCurrentIndex(max(0, len(analysis.assessments) - 1))
        self.check_source.blockSignals(False)
        self.populate_checks()

    def populate_checks(self):
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        if not self._result_sets:
            self.tree.addTopLevelItem(QTreeWidgetItem(
                ["Run an analysis to populate governed checks."]))
            return
        index = max(0, min(self.check_source.currentIndex(), len(self._result_sets) - 1))
        results = self._result_sets[index][1]
        by_category = {}
        for result in results:
            by_category.setdefault(result.check.category, []).append(result)
        mono_col = QFont(FONT_MONO)
        mono_col.setPixelSize(13)
        for category in sorted(by_category):
            group = QTreeWidgetItem([category])
            group.setFirstColumnSpanned(True)
            group.setFont(0, QFont(FONT_SANS, 10, QFont.DemiBold))
            group.setData(0, Qt.UserRole, "category")
            self.tree.addTopLevelItem(group)
            for result in by_category[category]:
                threshold = ("—" if result.threshold_applied is None else
                             f"{result.threshold_applied:g}")
                row = QTreeWidgetItem([
                    f"{result.check.id}  {result.check.name}",
                    result.display_value, threshold, result.status,
                    result.narrative])
                row.setData(0, Qt.UserRole, "result")
                row.setData(0, Qt.UserRole + 1, result.status)
                row.setToolTip(4, result.narrative)
                row.setFont(1, mono_col)
                row.setFont(2, mono_col)
                row.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
                row.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
                row.setBackground(3, QColor(STATUS_BG.get(result.status, "#EDF1F2")))
                row.setForeground(3, QColor(STATUS_FG.get(result.status, "#65747A")))
                row.setFont(3, QFont(FONT_SANS, 9, QFont.DemiBold))
                for finding in result.findings[:500]:
                    detail = f"{finding.object_name}  {finding.detail}".strip()
                    child = QTreeWidgetItem(
                        [finding.object_id, "", "", "", detail])
                    child.setData(0, Qt.UserRole, "finding")
                    row.addChild(child)
                group.addChild(row)
            group.setExpanded(True)
        self.tree.setSortingEnabled(True)
        self.filter_checks()

    def filter_checks(self, *_):
        query = self.check_search.text().strip().lower()
        status_filter = self.check_status.currentText()
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            visible_children = 0
            for j in range(group.childCount()):
                item = group.child(j)
                status = item.data(0, Qt.UserRole + 1) or ""
                haystack = " ".join(item.text(col) for col in range(5))
                for k in range(item.childCount()):
                    haystack += " " + " ".join(
                        item.child(k).text(col) for col in range(5))
                visible = (not query or query in haystack.lower()) and (
                    status_filter == "All statuses" or status == status_filter)
                item.setHidden(not visible)
                visible_children += int(visible)
            group.setHidden(visible_children == 0)

    def _populate_trends(self):
        analysis = self.current_result.analysis
        cards = list(getattr(self.current_card, "file_cards", [])) \
            if self.current_card else []
        health = [a.health_score for a in analysis.assessments]
        labels = [s.label() for s in analysis.schedules]
        self.health_sparkline.set_values(health, labels)
        self.trend_table.setRowCount(len(analysis.assessments))
        mono = QFont(FONT_MONO)
        mono.setPixelSize(13)
        right = Qt.AlignRight | Qt.AlignVCenter
        col_align = {1: Qt.AlignCenter, 2: right, 3: Qt.AlignCenter,
                     4: right, 5: right}
        for row, (schedule, assessment) in enumerate(
                zip(analysis.schedules, analysis.assessments)):
            card = cards[row] if row < len(cards) else None
            values = (
                schedule.label(),
                schedule.data_date.strftime("%Y-%m-%d") if schedule.data_date else "—",
                f"{assessment.health_score:.0f}",
                card.letter if card else "—",
                str(assessment.counts.get("FAIL", 0)),
                str(assessment.counts.get("WARNING", 0)),
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in col_align:
                    item.setFont(mono)
                    item.setTextAlignment(col_align[col])
                self.trend_table.setItem(row, col, item)
        if len(health) >= 2:
            delta = health[-1] - health[-2]
            self.movement_value.setText(f"{delta:+.1f} pts")
            direction = "improved" if delta > 0 else (
                "declined" if delta < 0 else "held steady")
            self.movement_note.setText(
                f"Latest health score {direction} from the prior update. "
                "Open Checks to inspect the underlying exceptions.")
        else:
            self.movement_value.setText("Single file")
            self.movement_note.setText(
                "Add another update to establish a trajectory.")

    def _populate_galleries(self):
        outputs = [path for path in self.current_result.outputs if os.path.exists(path)]
        path_names = {"fig_impact_waterfall.png", "fig_asbuilt_paths.png"}
        forensic_names = {
            "fig_halfstep.png", "fig_daily_ledger.png", "fig_robustness.png",
            "fig_sra_scurve.png", "fig_sra_tornado.png",
        }
        self._fill_gallery(self.paths_grid,
                           [p for p in outputs if os.path.basename(p) in path_names],
                           "cockpit.html")
        self._fill_forensics_gallery(
            [p for p in outputs if os.path.basename(p) in forensic_names])

    def _engine_validation_failed(self) -> bool:
        """True when the current run's SET-02 check reports a network-validation
        failure (engine_is_valid=False) — a genuine schedule defect, distinct
        from a merely low match rate.

        Read from the real check finding, not a match-rate proxy: a
        valid-but-fully-divergent schedule also scores 0.0%, so the rate cannot
        classify the cause.
        """
        try:
            assessments = self.current_result.analysis.assessments
        except AttributeError:
            return False
        if not assessments:
            return False
        for result in assessments[-1].results:
            if "network validation failed" in (result.narrative or "").lower():
                return True
            for finding in getattr(result, "findings", ()):
                if "network validation" in (
                        getattr(finding, "object_name", "") or "").lower():
                    return True
        return False

    def _fill_forensics_gallery(self, images: list[str]):
        _clear_layout(self.forensics_grid)
        row = col = 0
        for path in images:
            title = Path(path).stem.replace("fig_", "").replace("_", " ").title()
            card = FigureCard(title, path)
            card.open_requested.connect(open_local)
            self.forensics_grid.addWidget(card, row, col)
            col += 1
            if col == 2:
                row, col = row + 1, 0

        groups = group_blockers(
            self.current_result.messages,
            network_validation_failed=self._engine_validation_failed())
        diagnostics = [m for group in groups for m in group.messages]
        if diagnostics or not images:
            if col:
                row += 1
            card, lay = _card()
            heading = QHBoxLayout()
            title = QLabel(
                "Partial forensic output" if images
                else "Forensics unavailable for this run")
            title.setObjectName("sectionTitle")
            heading.addWidget(title)
            heading.addStretch()
            heading.addWidget(StatusPill(
                "PARTIAL" if images else "NOT GENERATED", "warning"))
            lay.addLayout(heading)

            self.forensics_diagnostic_label = None
            if groups:
                intro = QLabel(
                    "The standard assessment completed, but one or more governed "
                    "forensic exhibits were not produced. They are grouped below "
                    "by cause:")
                intro.setWordWrap(True)
                lay.addWidget(intro)

                for group in groups:
                    group_head = QHBoxLayout()
                    group_title = QLabel(group.category.title)
                    group_title.setObjectName("sectionTitle")
                    group_head.addWidget(group_title)
                    group_head.addStretch()
                    group_head.addWidget(
                        StatusPill(group.category.pill, group.category.tone))
                    lay.addLayout(group_head)

                    guidance = QLabel(group.category.guidance)
                    guidance.setObjectName("muted")
                    guidance.setWordWrap(True)
                    lay.addWidget(guidance)

                    bullets = QLabel(
                        "\n".join(f"\u2022 {m}" for m in group.messages))
                    bullets.setObjectName("privilegedWarning")
                    bullets.setWordWrap(True)
                    bullets.setTextInteractionFlags(Qt.TextSelectableByMouse)
                    lay.addWidget(bullets)
                    # Back-compat handle for callers/tests to query a reason; the
                    # full set is always in forensics_status_text below.
                    if self.forensics_diagnostic_label is None:
                        self.forensics_diagnostic_label = bullets
            else:
                intro = QLabel(
                    "Forensic exhibits require at least two schedule updates and "
                    "a passing SET-02 engine-to-record validation handshake.")
                intro.setWordWrap(True)
                lay.addWidget(intro)
                self.forensics_diagnostic_label = QLabel(
                    "\u2022 Add two or more chronological updates, then run the "
                    "analysis again.")
                self.forensics_diagnostic_label.setObjectName("privilegedWarning")
                self.forensics_diagnostic_label.setWordWrap(True)
                self.forensics_diagnostic_label.setTextInteractionFlags(
                    Qt.TextSelectableByMouse)
                lay.addWidget(self.forensics_diagnostic_label)

            self.forensics_safeguard_label = QLabel(
                "No forensic values were substituted. Standard checks, the Report "
                "Card, and other successfully generated outputs remain available. "
                "Open Checks and select each update's SET-02 row for per-file status.")
            self.forensics_safeguard_label.setObjectName("muted")
            self.forensics_safeguard_label.setWordWrap(True)
            lay.addWidget(self.forensics_safeguard_label)
            actions = QHBoxLayout()
            files = QPushButton("Review selected files")
            files.clicked.connect(lambda: self.navigate("files"))
            actions.addWidget(files)
            output = QPushButton("Open output folder")
            output.clicked.connect(lambda: open_local(self.out_dir))
            actions.addWidget(output)
            actions.addStretch()
            lay.addLayout(actions)
            self.forensics_grid.addWidget(card, row, 0, 1, 2)

        self.forensics_status_text = "\n".join(diagnostics)
        self.forensics_grid.setColumnStretch(0, 1)
        self.forensics_grid.setColumnStretch(1, 1)
        self.forensics_grid.setRowStretch(row + 1, 1)

    def _fill_gallery(self, grid: QGridLayout, images: list[str], html_name=None):
        _clear_layout(grid)
        row = col = 0
        for path in images:
            title = Path(path).stem.replace("fig_", "").replace("_", " ").title()
            card = FigureCard(title, path)
            card.open_requested.connect(open_local)
            grid.addWidget(card, row, col)
            col += 1
            if col == 2:
                row, col = row + 1, 0
        if html_name:
            html = next((p for p in self.current_result.outputs
                         if os.path.basename(p) == html_name and os.path.exists(p)), None)
            if html:
                card, lay = _card()
                title = QLabel("Interactive Network Cockpit")
                title.setObjectName("sectionTitle")
                lay.addWidget(title)
                note = QLabel(
                    "Explore schedule topology, critical paths, and update movement "
                    "in the pipeline-generated interactive cockpit.")
                note.setObjectName("muted")
                note.setWordWrap(True)
                lay.addWidget(note)
                button = QPushButton("Open interactive cockpit")
                button.setObjectName("primaryButton")
                button.clicked.connect(lambda checked=False, p=html: open_local(p))
                lay.addWidget(button)
                lay.addStretch()
                grid.addWidget(card, row, col)
                col += 1
        if not images and not html_name:
            empty = EmptyState(
                "No visuals generated",
                "This run did not produce a compatible exhibit. Review the run "
                "messages and SET-02 handshake status.", glyph="paths")
            grid.addWidget(empty, 0, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(max(row + 1, 1), 1)

    # --------------------------------------------------------------- actions
    def open_output(self):
        if self.out_dir:
            open_local(self.out_dir)

    def show_about(self):
        QMessageBox.about(
            self, "About ScheduleIQ",
            f"<h2>ScheduleIQ <span style='color:#16879A'>v{__version__}</span></h2>"
            "<p>Schedule quality, health, trend, path, forensic-delay, and risk "
            "analysis for Primavera P6 and Microsoft Project.</p>"
            "<p>Every governed check is documented in the Metric & Heuristic "
            "Matrix with its definition, threshold, and source reference.</p>"
            "<p><b>Analytical observations, not causation, entitlement, or "
            "quantum opinions.</b></p>")


def run_gui() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    window = MainWindow()
    window.show()
    if os.environ.get("SCHEDULEIQ_SMOKE_TEST") == "1":
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())
