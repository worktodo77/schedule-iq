"""ScheduleIQ desktop visual system.

The GUI keeps presentation concerns here so analytics and report generation stay
untouched.  Both palettes use the same semantic roles and teal brand accent.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette


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
    "light", "#F3F6F8", "#102A31", "#FFFFFF", "#F7F9FA", "#DCE4E7",
    "#17262B", "#65747A", "#16879A", "#0E7182", "#E5F5F7", "#23856D",
    "#E7F5F0", "#B7791F", "#FFF4DC", "#C85050", "#FCEBEC", "#3979A8",
    "#EAF2F8",
)

DARK = Theme(
    "dark", "#0C1418", "#091115", "#132027", "#17272E", "#2A3B43",
    "#E9F1F3", "#91A2A9", "#2FB0C2", "#47C4D3", "#17383F", "#4EC19C",
    "#17372F", "#E1A84C", "#3B301D", "#EF7777", "#402327", "#68A9D5",
    "#1C3342",
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
    return f"""
    * {{
        font-family: "Segoe UI";
        font-size: 13px;
        color: {t.text};
    }}
    QMainWindow, QWidget#appCanvas {{ background: {t.canvas}; }}
    QWidget#sidebar {{ background: {t.sidebar}; border: 0; }}
    QLabel#brandMark {{ color: #FFFFFF; font-size: 22px; font-weight: 700; }}
    QLabel#brandSub {{ color: #9CB4BA; font-size: 10px; font-weight: 600;
        letter-spacing: 1px; }}
    QLabel#pageTitle {{ font-size: 24px; font-weight: 700; color: {t.text}; }}
    QLabel#pageSubtitle {{ color: {t.muted}; font-size: 13px; }}
    QLabel#sectionTitle {{ font-size: 15px; font-weight: 650; }}
    QLabel#metricValue {{ font-size: 25px; font-weight: 700; }}
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
        padding: 8px 13px; font-weight: 600;
    }}
    QPushButton:hover {{ background: {t.surface_alt}; border-color: {t.accent}; }}
    QPushButton:focus {{ border: 2px solid {t.accent}; padding: 7px 12px; }}
    QPushButton:disabled {{ color: {t.muted}; background: {t.surface_alt}; }}
    QPushButton#primaryButton {{ background: {t.accent}; color: white;
        border-color: {t.accent}; padding: 9px 18px; }}
    QPushButton#primaryButton:hover {{ background: {t.accent_hover}; }}
    QPushButton#ghostButton {{ background: transparent; }}
    QPushButton#themeButton {{ border-radius: 16px; min-width: 32px;
        max-width: 32px; min-height: 32px; padding: 0; }}
    QPushButton#navButton {{
        background: transparent; color: #AFC2C7; border: 0; border-radius: 8px;
        text-align: left; padding: 10px 13px; font-size: 13px; font-weight: 600;
    }}
    QPushButton#navButton:hover {{ background: #17373F; color: white; }}
    QPushButton#navButton:checked {{ background: #1B4650; color: white;
        border-left: 3px solid #42C4D2; padding-left: 10px; }}

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
        font-size: 11px; font-weight: 700; }}
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
    theme = DARK if name == "dark" else LIGHT
    app.setPalette(palette(theme))
    app.setStyleSheet(stylesheet(theme))
    app.setProperty("scheduleiqTheme", theme.name)
    return theme
