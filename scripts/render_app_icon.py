"""Render the committed SVG brand mark to the PNG used by PyInstaller."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "scheduleiq" / "gui" / "assets"


def main() -> int:
    source = ASSETS / "scheduleiq_icon.svg"
    target = ASSETS / "scheduleiq_icon.png"
    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise RuntimeError(f"invalid SVG: {source}")
    image = QImage(256, 256, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, 256, 256))
    painter.end()
    if not image.save(str(target), "PNG"):
        raise RuntimeError(f"could not save {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
