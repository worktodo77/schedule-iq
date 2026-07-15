"""Capture all major ScheduleIQ views in light and dark themes.

Run from the repository root. Images are written to ``docs/ui`` using a real
demo analysis result; no mocked score or check data is used.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtWidgets import QApplication

from scheduleiq.gui.app import MainWindow
from scheduleiq.runner import run


def main() -> int:
    screenshots = ROOT / "docs" / "ui"
    screenshots.mkdir(parents=True, exist_ok=True)
    fixtures = ROOT / "tests" / "fixtures"
    runtime = Path(tempfile.mkdtemp(prefix="scheduleiq-ui-"))
    try:
        result = run(
            [str(fixtures / "demo_hs1.xer"), str(fixtures / "demo_hs2.xer")],
            str(runtime / "outputs"),
            make_pdf=False,
            events_csv=str(fixtures / "events_sample.csv"),
            responsibility_csv=str(fixtures / "responsibility_sample.csv"),
            internal_workbook=True,
        )
        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        window.resize(1440, 900)
        window._add_paths([
            str(fixtures / "demo_hs1.xer"), str(fixtures / "demo_hs2.xer")])
        window.internal_cb.setChecked(True)
        window.show_results(result)
        window.show()
        app.processEvents()
        for theme in ("light", "dark"):
            window.set_theme(theme)
            for key, _, _ in window.NAV:
                window.navigate(key)
                app.processEvents()
                target = screenshots / f"{theme}_{key}.png"
                if not window.grab().save(str(target)):
                    raise RuntimeError(f"could not save {target}")
        window.close()
    finally:
        shutil.rmtree(runtime, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
