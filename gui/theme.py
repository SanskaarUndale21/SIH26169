"""One shared dark theme for the desktop GUI, applied once via
QApplication.setStyleSheet() at startup (main.py). Consistent palette,
typography, spacing, and hover/focus states across every widget instead
of Qt's default platform styling.

Material language borrowed from a reference "instrument panel" design
(graphite base + a single warm accent + glow, not a flat generic-blue
Bootstrap look): deep graphite backgrounds, one accent colour used for
every interactive/positive state (copper), pewter for
processing/neutral-busy states, glow via border colour + a drop-shadow
effect applied in code (gui/main_window.py) since Qt Widgets has no CSS
backdrop-filter/box-shadow equivalent -- QSS approximates the "glass
panel" look with layered flat surface colours and coloured borders
instead of real blur.

Palette mirrors web/control_page.py's dark theme so the desktop app and
the browser control page read as the same product.
"""
from __future__ import annotations

# --- Palette ---
BG = "#0a0a0c"
SURFACE = "#131316"
SURFACE_RAISED = "#191a1e"
BORDER = "#2a241d"
BORDER_LIGHT = "#3a2f22"
TEXT = "#ece8e2"
TEXT_MUTED = "#b8bcc4"
TEXT_FAINT = "#6b6e75"

# The one accent: molten copper (replaces a generic blue) -- used for
# every "engaged / positive / primary action" state.
ACCENT = "#d98a4f"
ACCENT_BRIGHT = "#ffb066"
ACCENT_DIM = "#8a5230"
ACCENT_WASH = "rgba(217, 138, 79, 0.14)"

# Secondary functional hue: pewter, for "processing / busy" only -- never
# used for a primary action, so accent colour alone always tells you
# what's interactive vs. what's just status.
PEWTER = "#93a1b0"
PEWTER_BRIGHT = "#c3ccd6"

OK = "#7fb08a"
OK_TEXT = "#9fd4aa"
BAD = "#c9634f"
BAD_TEXT = "#e8ab9d"
WARN = "#d9a94f"

FONT_FAMILY = '"Segoe UI Semibold", "Segoe UI", -apple-system, "Helvetica Neue", Arial, sans-serif'
MONO_FAMILY = '"Consolas", "SF Mono", monospace'

STYLESHEET = f"""
* {{
    font-family: {FONT_FAMILY};
    font-size: 13px;
    color: {TEXT};
}}

QMainWindow, QWidget {{
    background-color: {BG};
}}

QWidget#headerBar {{
    background-color: {SURFACE};
    border-bottom: 1px solid {BORDER};
}}

/* --- Group boxes --- */
QGroupBox {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
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
    border-radius: 10px;
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
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 500;
}}
QTabBar::tab:selected {{
    background-color: {SURFACE};
    color: {ACCENT_BRIGHT};
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
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {BORDER_LIGHT};
    border-color: {ACCENT};
    color: {ACCENT_BRIGHT};
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
    color: #14100b;
    font-weight: 700;
}}
QPushButton#startBtn:hover {{ background-color: {ACCENT_BRIGHT}; }}
QPushButton#stopBtn {{
    background-color: {SURFACE_RAISED};
    border-color: {BAD};
    color: {BAD_TEXT};
}}
QPushButton#stopBtn:hover {{ background-color: #2a1714; }}

/* --- Inputs --- */
QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 6px;
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
    selection-background-color: {ACCENT_DIM};
    selection-color: {ACCENT_BRIGHT};
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
    background: {ACCENT_BRIGHT};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: {TEXT};
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
    color: {ACCENT_BRIGHT};
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
    background: {ACCENT_DIM};
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
    font-family: {MONO_FAMILY};
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
