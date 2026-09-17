"""One shared dark theme for the desktop GUI, applied once via
QApplication.setStyleSheet() at startup (main.py). Consistent palette,
typography, spacing, and hover/focus states across every widget instead
of Qt's default platform styling -- this file is the single place that
palette lives, so every panel (config, video, dashboard, 3D) reads as
one designed product rather than a pile of default-styled widgets.

Palette mirrors web/control_page.py's dark theme so the desktop app and
the browser control page look like the same product, not two unrelated
UIs -- same background/surface/border/accent/status colours.
"""
from __future__ import annotations

# --- Palette (kept in one place so both this stylesheet and any
# programmatic colour use -- e.g. gui/dashboard_panel.py's metric-card
# verdict colours -- can reference the same values) ---
BG = "#0b0d12"
SURFACE = "#12141a"
SURFACE_RAISED = "#171a21"
BORDER = "#242833"
BORDER_LIGHT = "#2e3340"
TEXT = "#e6e8ec"
TEXT_MUTED = "#8b90a0"
TEXT_FAINT = "#5b6070"
ACCENT = "#3b82f6"
ACCENT_HOVER = "#2563eb"
ACCENT_TEXT = "#93c5fd"
OK = "#22c55e"
OK_TEXT = "#4ade80"
BAD = "#ef4444"
BAD_TEXT = "#f87171"
WARN = "#eab308"

FONT_FAMILY = '"Segoe UI", -apple-system, "Helvetica Neue", Arial, sans-serif'

STYLESHEET = f"""
* {{
    font-family: {FONT_FAMILY};
    font-size: 13px;
    color: {TEXT};
}}

QMainWindow, QWidget {{
    background-color: {BG};
}}

QWidget#leftPane, QWidget#centerPane {{
    background-color: {BG};
}}

QWidget#headerBar {{
    background-color: {SURFACE};
    border-bottom: 1px solid {BORDER};
}}

/* --- Group boxes (config panel sections) --- */
QGroupBox {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 10px;
    padding: 14px 10px 10px 10px;
    font-weight: 600;
    font-size: 12px;
    color: {TEXT_MUTED};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {TEXT};
    background-color: {BG};
}}

/* --- Tabs --- */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    background-color: {SURFACE};
    top: -1px;
}}
QTabBar::tab {{
    background-color: transparent;
    color: {TEXT_MUTED};
    padding: 8px 16px;
    margin-right: 2px;
    border: 1px solid transparent;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 500;
}}
QTabBar::tab:selected {{
    background-color: {SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT};
    background-color: {SURFACE_RAISED};
}}
QTabBar::scroller {{ width: 24px; }}
QTabBar QToolButton {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 4px;
}}

/* --- Buttons --- */
QPushButton {{
    background-color: {SURFACE_RAISED};
    color: {TEXT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {BORDER_LIGHT};
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background-color: {BORDER};
}}
QPushButton:disabled {{
    color: {TEXT_FAINT};
    background-color: {SURFACE};
    border-color: {BORDER};
}}
QPushButton#startBtn {{
    background-color: {ACCENT};
    border-color: {ACCENT};
    color: white;
}}
QPushButton#startBtn:hover {{ background-color: {ACCENT_HOVER}; }}
QPushButton#stopBtn {{
    background-color: {SURFACE_RAISED};
    border-color: {BAD};
    color: {BAD_TEXT};
}}
QPushButton#stopBtn:hover {{ background-color: #241414; }}

/* --- Inputs: combo/spin/slider/checkbox --- */
QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 5px;
    padding: 4px 8px;
    min-height: 22px;
}}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER_LIGHT};
    selection-background-color: {ACCENT};
    color: {TEXT};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background-color: {SURFACE};
    border: none;
    width: 16px;
}}

QSlider::groove:horizontal {{
    height: 4px;
    background: {BORDER_LIGHT};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {TEXT};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: {ACCENT_TEXT};
}}

QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER_LIGHT};
    border-radius: 4px;
    background: {SURFACE_RAISED};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}

/* --- Config panel group sidebar --- */
QListWidget#groupList {{
    background-color: {SURFACE};
    border: none;
    border-right: 1px solid {BORDER};
    outline: none;
    padding: 6px 0;
}}
QListWidget#groupList::item {{
    padding: 9px 14px;
    color: {TEXT_MUTED};
    border-left: 2px solid transparent;
}}
QListWidget#groupList::item:selected {{
    background-color: {SURFACE_RAISED};
    color: {TEXT};
    border-left: 2px solid {ACCENT};
}}
QListWidget#groupList::item:hover:!selected {{
    background-color: {SURFACE_RAISED};
    color: {TEXT};
}}

/* --- Labels & scroll areas --- */
QLabel {{
    background: transparent;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: {BG};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_LIGHT};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TEXT_FAINT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* --- Status bar --- */
QStatusBar {{
    background-color: {SURFACE};
    border-top: 1px solid {BORDER};
    color: {TEXT_MUTED};
    font-size: 12px;
}}

/* --- Splitter handle --- */
QSplitter::handle {{
    background-color: {BORDER};
    width: 2px;
}}
QSplitter::handle:hover {{
    background-color: {ACCENT};
}}
"""
