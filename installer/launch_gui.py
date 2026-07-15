"""Absolute-import launcher used by the Windows PyInstaller bundle."""
from __future__ import annotations

import os
import sys


def main() -> int:
    if "--demo-smoke" in sys.argv:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        index = sys.argv.index("--demo-smoke")
        try:
            fixture = sys.argv[index + 1]
            out_dir = sys.argv[index + 2]
        except IndexError:
            return 2
        from PySide6.QtWidgets import QApplication
        from scheduleiq.gui.app import MainWindow
        from scheduleiq.runner import run

        app = QApplication.instance() or QApplication([])
        result = run([fixture], out_dir, make_pdf=False, no_cockpit=True)
        window = MainWindow()
        window.show_results(result)
        app.processEvents()
        valid = (window.current_card is not None
                 and window.tree.topLevelItemCount() > 0
                 and window.open_btn.isEnabled())
        window.close()
        return 0 if valid else 3
    if "--smoke-test" in sys.argv:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
        from scheduleiq.gui.app import MainWindow

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        window.show()
        QTimer.singleShot(100, app.quit)
        return app.exec()
    from scheduleiq.gui.app import run_gui
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
