"""Headless launch and populated-demo smoke coverage for the desktop app."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from scheduleiq.gui.app import MainWindow
from scheduleiq.runner import run


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_main_window_instantiates_and_populates_from_demo_run(qapp, tmp_path):
    result = run(
        [str(FIXTURES / "demo_baseline.xer")],
        str(tmp_path / "output"),
        make_pdf=False,
        no_cockpit=True,
    )
    window = MainWindow()
    window.show_results(result)
    qapp.processEvents()

    assert window.stack.count() == 7
    assert window.current_result is result
    assert window.current_card is not None
    assert window.gauge.score == pytest.approx(window.current_card.overall)
    assert window.check_source.count() == 1
    assert window.tree.topLevelItemCount() > 0
    assert window.trend_table.rowCount() == 1
    assert window.open_btn.isEnabled()
    assert "Done" in window.status_bar.text()
    window.close()


def test_cli_gui_route_uses_desktop_entrypoint(monkeypatch):
    from scheduleiq import cli
    import scheduleiq.gui.app as gui_app

    called = []
    monkeypatch.setattr(gui_app, "run_gui", lambda: called.append(True) or 0)
    assert cli.main(["gui"]) == 0
    assert called == [True]
