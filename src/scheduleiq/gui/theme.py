"""ScheduleIQ desktop visual system — the "Instrument" design language.

Presentation lives here so analytics and report generation stay untouched.
Typography is IBM Plex, bundled under ``gui/assets/fonts``: IBM Plex Sans for
text and IBM Plex Mono for figures and identifiers — a precise, authoritative
"instrument" feel with the teal brand accent, in matched light and dark
palettes.  Both palettes use the same semantic roles.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontDatabase, QPalette


FONT_SANS = "IBM Plex Sans"
FONT_MONO = "IBM Plex Mono"

_FONT_DIR = Path(__file__).with_name("assets") / "fonts"
_fonts_loaded = False


def load_fonts() -> None:
    """Register the bundled IBM Plex families once.

    Idempotent; requires a live QApplication.  If the bundled files are missing
    the app simply falls back to the QSS font stack (Segoe UI), so a missing
    asset degrades gracefully rather than failing to launch.
    """
    global _fonts_loaded
    if _fonts_loaded:
        return
    if _FONT_DIR.is_dir():
        for ttf in sorted(_FONT_DIR.glob("*.ttf")):
            QFontDatabase.addApplicationFont(str(ttf))
    _fonts_loaded = True


@dataclass(frozen=True)
class Theme:
    name: str
    canvas: str
    sidebar: str
    surface: str
    surface_alt: str
    border: str
    text: str
    muted: str
    accent: str
    accent_hover: str
    accent_soft: str
    success: str
    success_soft: str
    warning: str
    warning_soft: str
    danger: str
    danger_soft: str
    info: str
    info_soft: str


LIGHT = Theme(
    "light", "#F1F4F6", "#0E2429", "#FFFFFF", "#F4F7F8", "#D8E0E4",
    "#16242A", "#5F6E74", "#0E7C8E", "#0A6576", "#E1F4F6", "#1E7D66",
    "#E4F4EF", "#A96D16", "#FBF0D8", "#C0484C", "#FBE9EA", "#34719E",
    "#E7F1F7",
)

DARK = Theme(
    "dark", "#0E151A", "#0A1015", "#172129", "#1E2A33", "#29373F",
    "#E6EEF2", "#8A9BA4", "#2FB0C2", "#46C3D3", "#14333B", "#55C2A0",
    "#163429", "#E1A84C", "#372D1A", "#EF8585", "#3C2225", "#6BAAD6",
    "#17303E",
)


def system_theme(app) -> str:
    """Return the OS preference where Qt exposes it; otherwise light."""
    try:
        scheme = app.styleHints().colorScheme()
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"
    except (AttributeError, RuntimeError):
        return "light"


def palette(theme: Theme) -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, QColor(theme.canvas))
    p.setColor(QPalette.WindowText, QColor(theme.text))
    p.setColor(QPalette.Base, QColor(theme.surface))
    p.setColor(QPalette.AlternateBase, QColor(theme.surface_alt))
    p.setColor(QPalette.ToolTipBase, QColor(theme.surface))
    p.setColor(QPalette.ToolTipText, QColor(theme.text))
    p.setColor(QPalette.Text, QColor(theme.text))
    p.setColor(QPalette.Button, QColor(theme.surface))
    p.setColor(QPalette.ButtonText, QColor(theme.text))
    p.setColor(QPalette.Highlight, QColor(theme.accent))
    p.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    p.setColor(QPalette.PlaceholderText, QColor(theme.muted))
    return p


def stylesheet(t: Theme) -> str:
    sans = f'"{FONT_SANS}", "Segoe UI", "Helvetica Neue", sans-serif'
    mono = f'"{FONT_MONO}", "Cascadia Mono", "Consolas", monospace'
    return f"""
    * {{
        font-family: {sans};
        font-size: 13px;
        color: {t.text};
    }}
    QMainWindow, QWidget#appCanvas {{ background: {t.canvas}; }}
    QWidget#sidebar {{ background: {t.sidebar}; border: 0; }}
    QLabel#brandMark {{ color: #FFFFFF; font-size: 20px; font-weight: 600;
        letter-spacing: 0.2px; }}
    QLabel#brandSub {{ color: #93ACB2; font-size: 10px; font-weight: 600;
        letter-spacing: 0.7px; }}
    QLabel#pageTitle {{ font-size: 24px; font-weight: 600; color: {t.text};
        letter-spacing: -0.4px; }}
    QLabel#pageSubtitle {{ color: {t.muted}; font-size: 13px; }}
    QLabel#sectionTitle {{ font-size: 14px; font-weight: 600;
        letter-spacing: 0.1px; }}
    QLabel#metricValue {{ font-family: {mono}; font-size: 25px; font-weight: 600;
        letter-spacing: -0.5px; }}
    QLabel#monoValue, QLabel[mono="true"] {{ font-family: {mono}; }}
    QLabel#muted, QLabel.muted {{ color: {t.muted}; }}
    QLabel#warningText {{ color: {t.warning}; }}
    QLabel#privilegedWarning {{ color: {t.warning}; background: {t.warning_soft};
        border: 1px solid {t.warning}; border-radius: 8px; padding: 9px; }}

    QFrame#card, QFrame#dropCard, QFrame#galleryCard {{
        background: {t.surface}; border: 1px solid {t.border};
        border-radius: 12px;
    }}
    QFrame#dropCard[dragActive="true"] {{
        border: 2px dashed {t.accent}; background: {t.accent_soft};
    }}
    QFrame#topBar {{ background: {t.canvas}; border: 0; }}
    QFrame#divider {{ background: {t.border}; max-height: 1px; }}

    QPushButton {{
        background: {t.surface}; border: 1px solid {t.border}; border-radius: 8px;
        padding: 8px 13px; font-weight: 500;
    }}
    QPushButton:hover {{ background: {t.surface_alt}; border-color: {t.accent}; }}
    QPushButton:focus {{ border: 2px solid {t.accent}; padding: 7px 12px; }}
    QPushButton:disabled {{ color: {t.muted}; background: {t.surface_alt}; }}
    QPushButton#primaryButton {{ background: {t.accent}; color: white;
        border-color: {t.accent}; padding: 9px 18px; font-weight: 600; }}
    QPushButton#primaryButton:hover {{ background: {t.accent_hover}; }}
    QPushButton#ghostButton {{ background: transparent; }}
    QPushButton#themeButton {{ border-radius: 16px; min-width: 32px;
        max-width: 32px; min-height: 32px; padding: 0; }}
    QPushButton#navButton {{
        background: transparent; color: #AFC2C7; border: 0; border-radius: 8px;
        text-align: left; padding: 10px 13px; font-size: 13px; font-weight: 500;
    }}
    QPushButton#navButton:hover {{ background: #16323A; color: white; }}
    QPushButton#navButton:checked {{ background: #1A4550; color: white;
        border-left: 3px solid {t.accent}; padding-left: 10px; font-weight: 600; }}

    QLineEdit, QComboBox, QSpinBox {{
        background: {t.surface}; border: 1px solid {t.border}; border-radius: 8px;
        padding: 8px 10px; selection-background-color: {t.accent};
    }}
    QLineEdit:focus, QComboBox:focus {{ border: 2px solid {t.accent};
        padding: 7px 9px; }}
    QComboBox::drop-down {{ border: 0; width: 24px; }}
    QComboBox QAbstractItemView {{ background: {t.surface}; border: 1px solid {t.border};
        selection-background-color: {t.accent_soft}; selection-color: {t.text}; }}

    QListWidget, QTreeWidget, QTableWidget {{
        background: {t.surface}; alternate-background-color: {t.surface_alt};
        border: 1px solid {t.border}; border-radius: 10px; outline: 0;
        selection-background-color: {t.accent_soft}; selection-color: {t.text};
    }}
    QTreeWidget::item, QListWidget::item {{ padding: 7px; border-radius: 5px; }}
    QTreeWidget::item:hover, QListWidget::item:hover {{ background: {t.surface_alt}; }}
    QHeaderView::section {{ background: {t.surface_alt}; color: {t.muted};
        padding: 9px; border: 0; border-bottom: 1px solid {t.border};
        font-size: 11px; font-weight: 600; letter-spacing: 0.6px; }}
    QTableCornerButton::section {{ background: {t.surface_alt}; border: 0; }}

    QScrollArea {{ border: 0; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t.border}; min-height: 30px;
        border-radius: 4px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QProgressBar {{ background: {t.surface_alt}; border: 0; border-radius: 3px;
        min-height: 6px; max-height: 6px; text-align: center; }}
    QProgressBar::chunk {{ background: {t.accent}; border-radius: 3px; }}
    QToolTip {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border};
        padding: 5px; }}
    QMenuBar {{ background: {t.canvas}; }}
    QMenuBar::item:selected, QMenu::item:selected {{ background: {t.accent_soft}; }}
    QMenu {{ background: {t.surface}; border: 1px solid {t.border}; padding: 5px; }}
    QDialog {{ background: {t.canvas}; }}
    """


def apply_theme(app, name: str) -> Theme:
    load_fonts()
    theme = DARK if name == "dark" else LIGHT
    app.setPalette(palette(theme))
    app.setStyleSheet(stylesheet(theme))
    app.setProperty("scheduleiqTheme", theme.name)
    return theme
