"""Custom-painted, dependency-free visual widgets for the desktop dashboard."""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QIcon, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

SANS = "IBM Plex Sans"
MONO = "IBM Plex Mono"
ICON_FONT = "tabler-icons"

# Semantic name -> Tabler glyph codepoint (from the bundled subset font).
_ICON_CODES = {
    "files": 0xEDEF, "report": 0xEAB1, "checks": 0xF074, "trends": 0xEB43,
    "paths": 0xEB17, "forensics": 0xEF64, "settings": 0xEB20,
    "sun": 0xEB30, "moon": 0xEAF8, "plus": 0xEB0B,
}


def icon_pixmap(name: str, size: int = 20, color: str = "#B4C6CB") -> QPixmap:
    """Render a bundled Tabler glyph to a crisp DPR-2 QPixmap.

    Painted at 2x with a device-pixel-ratio pixmap so it stays sharp on
    high-DPI displays.  Returns a null pixmap for an unknown name rather than
    raising, so a missing mapping degrades gracefully.
    """
    code = _ICON_CODES.get(name)
    if code is None:
        return QPixmap()
    # Ensure the bundled icon font is registered before we bake the glyph into a
    # pixmap — icons built during window construction run before the theme (and
    # its font loading) is applied, which would otherwise render tofu.
    from .theme import load_fonts
    load_fonts()
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    glyph_font = QFont(ICON_FONT)
    glyph_font.setPixelSize(int(size * dpr * 0.92))
    p.setFont(glyph_font)
    p.setPen(QColor(color))
    p.drawText(pm.rect(), Qt.AlignCenter, chr(code))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, size: int = 20, color: str = "#B4C6CB") -> QIcon:
    """Render a bundled Tabler glyph to a crisp QIcon at the given px size."""
    pm = icon_pixmap(name, size, color)
    return QIcon(pm) if not pm.isNull() else QIcon()


def _theme(widget) -> str:
    app = widget.window().windowHandle()
    del app
    from PySide6.QtWidgets import QApplication
    return QApplication.instance().property("scheduleiqTheme") or "light"


def semantic_colors(widget) -> dict[str, str]:
    dark = _theme(widget) == "dark"
    return {
        "text": "#E6EEF2" if dark else "#16242A",
        "muted": "#8A9BA4" if dark else "#5F6E74",
        "track": "#29373F" if dark else "#E3EAEC",
        "accent": "#2FB0C2" if dark else "#0E7C8E",
        "success": "#55C2A0" if dark else "#1E7D66",
        "warning": "#E1A84C" if dark else "#A96D16",
        "danger": "#EF8585" if dark else "#C0484C",
    }


class ScoreGauge(QWidget):
    """Compact donut gauge with a centered letter and numeric score."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.score = 0.0
        self.letter = "—"
        self.setMinimumSize(210, 210)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def set_score(self, score: float, letter: str):
        self.score = max(0.0, min(100.0, float(score)))
        self.letter = letter
        self.update()

    def paintEvent(self, event):
        del event
        c = semantic_colors(self)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height()) - 24
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2,
                      side, side)
        pen = QPen(QColor(c["track"]), 14, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 0, 360 * 16)
        tone = c["success"] if self.score >= 85 else c["accent"]
        if self.score < 70:
            tone = c["warning"]
        if self.score < 55:
            tone = c["danger"]
        p.setPen(QPen(QColor(tone), 14, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, 90 * 16, -int(360 * 16 * self.score / 100))
        p.setPen(QColor(c["text"]))
        f = QFont(SANS, 40, QFont.DemiBold)
        p.setFont(f)
        letter_rect = QRectF(rect.left(), rect.center().y() - 54,
                             rect.width(), 64)
        p.drawText(letter_rect, Qt.AlignCenter, self.letter)
        p.setPen(QColor(c["muted"]))
        p.setFont(QFont(MONO, 12, QFont.Medium))
        score_rect = QRectF(rect.left(), rect.center().y() + 14,
                            rect.width(), 28)
        p.drawText(score_rect, Qt.AlignCenter, f"{self.score:.0f} / 100")


class Sparkline(QWidget):
    """Small anti-aliased line chart for per-update trends."""

    def __init__(self, values=None, labels=None, parent=None):
        super().__init__(parent)
        self.values = list(values or [])
        self.labels = list(labels or [])
        self.setMinimumHeight(130)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_values(self, values, labels=None):
        self.values = [float(v) for v in values]
        self.labels = list(labels or [])
        self.update()

    def paintEvent(self, event):
        del event
        c = semantic_colors(self)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(18, 12, max(1, self.width() - 36), max(1, self.height() - 34))
        p.setPen(QPen(QColor(c["track"]), 1))
        for frac in (0.0, .5, 1.0):
            y = r.top() + r.height() * frac
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        if not self.values:
            p.setPen(QColor(c["muted"]))
            p.drawText(r, Qt.AlignCenter, "Run an analysis to see the trend")
            return
        lo, hi = min(self.values), max(self.values)
        pad = max(4.0, (hi - lo) * .15)
        lo, hi = max(0.0, lo - pad), min(100.0, hi + pad)
        if math.isclose(lo, hi):
            lo, hi = max(0, lo - 5), min(100, hi + 5)
        points = []
        for i, value in enumerate(self.values):
            x = r.left() + (r.width() * i / max(1, len(self.values) - 1))
            y = r.bottom() - r.height() * ((value - lo) / max(.001, hi - lo))
            points.append(QPointF(x, y))
        area = QPainterPath(points[0])
        for pt in points[1:]:
            area.lineTo(pt)
        area.lineTo(QPointF(points[-1].x(), r.bottom()))
        area.lineTo(QPointF(points[0].x(), r.bottom()))
        area.closeSubpath()
        fill = QColor(c["accent"])
        fill.setAlpha(38)
        p.fillPath(area, fill)
        line = QPainterPath(points[0])
        for pt in points[1:]:
            line.lineTo(pt)
        p.setPen(QPen(QColor(c["accent"]), 3, Qt.SolidLine, Qt.RoundCap,
                      Qt.RoundJoin))
        p.drawPath(line)
        p.setBrush(QColor(c["accent"]))
        p.setPen(QPen(QColor("white"), 2))
        for pt in points:
            p.drawEllipse(pt, 4, 4)
        p.setPen(QColor(c["muted"]))
        p.setFont(QFont(SANS, 9))
        if self.labels:
            last = len(self.labels) - 1
            for i, label in enumerate(self.labels):
                if i not in (0, last) and len(self.labels) > 4:
                    continue
                x = points[i].x()
                text = str(label)[:24]
                # Anchor edge labels inward so they are never clipped by the
                # widget border — the first/last point sits at the chart margin,
                # so a centred label would overflow the left/right edge.
                if i == 0:
                    rect = QRectF(x - 6, r.bottom() + 5, 160, 18)
                    align = Qt.AlignLeft | Qt.AlignVCenter
                elif i == last:
                    rect = QRectF(x - 154, r.bottom() + 5, 160, 18)
                    align = Qt.AlignRight | Qt.AlignVCenter
                else:
                    rect = QRectF(x - 65, r.bottom() + 5, 130, 18)
                    align = Qt.AlignHCenter | Qt.AlignVCenter
                p.drawText(rect, align, text)


class CategoryBar(QWidget):
    def __init__(self, name: str, score: float | None, parent=None):
        super().__init__(parent)
        self.name, self.score = name, score
        self.setMinimumHeight(42)

    def paintEvent(self, event):
        del event
        c = semantic_colors(self)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor(c["text"]))
        p.setFont(QFont(SANS, 10, QFont.Medium))
        p.drawText(QRectF(0, 0, self.width() - 52, 18), Qt.AlignLeft, self.name)
        score = self.score
        p.setPen(QColor(c["muted"]))
        p.setFont(QFont(MONO, 10))
        p.drawText(QRectF(self.width() - 50, 0, 48, 18), Qt.AlignRight,
                   "—" if score is None else f"{score:.0f}")
        track = QRectF(0, 25, self.width(), 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(c["track"]))
        p.drawRoundedRect(track, 4, 4)
        if score is not None:
            tone = c["success"] if score >= 85 else c["accent"]
            if score < 70:
                tone = c["warning"]
            if score < 55:
                tone = c["danger"]
            p.setBrush(QColor(tone))
            p.drawRoundedRect(QRectF(track.left(), track.top(),
                                    track.width() * max(0, min(100, score)) / 100,
                                    track.height()), 4, 4)


class StatusPill(QLabel):
    """A soft status chip whose colors track the active theme.

    Both palettes carry the same semantic roles; the dark tones are the fix for
    the previous hardcoded light chips, which sat as pale blocks on dark cards.
    """

    _LIGHT = {
        "success": ("#1E7D66", "#E4F4EF"),
        "warning": ("#8A5712", "#FBF0D8"),
        "danger": ("#B23D45", "#FBE9EA"),
        "info": ("#34719E", "#E7F1F7"),
        "muted": ("#5F6E74", "#EAEEF0"),
    }
    _DARK = {
        "success": ("#5CC6A2", "#17372F"),
        "warning": ("#E4B463", "#3B301D"),
        "danger": ("#EF8B8B", "#402327"),
        "info": ("#7FB5DC", "#1C3342"),
        "muted": ("#9AAAB2", "#22303A"),
    }

    def __init__(self, text: str, tone: str, parent=None):
        super().__init__(text, parent)
        dark = (QApplication.instance().property("scheduleiqTheme") or
                "light") == "dark"
        table = self._DARK if dark else self._LIGHT
        fg, bg = table.get(tone, table["muted"])
        self.setStyleSheet(f"color:{fg}; background:{bg}; border-radius:10px; "
                           "padding:3px 9px; font-size:10px; font-weight:600;")
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)


class FigureCard(QFrame):
    open_requested = Signal(str)

    def __init__(self, title: str, path: str, parent=None):
        super().__init__(parent)
        self.setObjectName("galleryCard")
        self.path = path
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        head = QHBoxLayout()
        label = QLabel(title)
        label.setObjectName("sectionTitle")
        head.addWidget(label)
        head.addStretch()
        open_btn = QPushButton("Open")
        open_btn.setObjectName("ghostButton")
        open_btn.clicked.connect(lambda: self.open_requested.emit(self.path))
        head.addWidget(open_btn)
        lay.addLayout(head)
        preview = QLabel()
        preview.setAlignment(Qt.AlignCenter)
        preview.setMinimumHeight(230)
        pix = QPixmap(path)
        if pix.isNull():
            preview.setText("Preview unavailable")
        else:
            preview.setPixmap(pix.scaled(620, 300, Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation))
        lay.addWidget(preview, 1)


class EmptyState(QFrame):
    action_requested = Signal()

    def __init__(self, title: str, body: str, action: str = "", parent=None,
                 glyph: str = "report"):
        super().__init__(parent)
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 28, 28, 28)
        lay.addStretch()
        icon_lbl = QLabel()
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setPixmap(icon_pixmap(glyph, 46, "#4C6B73"))
        lay.addWidget(icon_lbl)
        ttl = QLabel(title)
        ttl.setObjectName("sectionTitle")
        ttl.setAlignment(Qt.AlignCenter)
        lay.addWidget(ttl)
        text = QLabel(body)
        text.setObjectName("muted")
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignCenter)
        lay.addWidget(text)
        if action:
            row = QHBoxLayout()
            row.addStretch()
            btn = QPushButton(action)
            btn.setObjectName("primaryButton")
            btn.clicked.connect(self.action_requested)
            row.addWidget(btn)
            row.addStretch()
            lay.addLayout(row)
        lay.addStretch()


def open_local(path: str):
    QDesktopServices.openUrl(Path(path).resolve().as_uri())
