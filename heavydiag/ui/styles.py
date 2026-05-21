"""
styles.py
---------
Global color palette and Qt stylesheet for HeavyDiag.
Dark theme inspired by professional diagnostic tool UIs.
"""

# --- Color palette ---
COLOR_BG_DARK        = "#0D1117"
COLOR_BG_PANEL       = "#161B22"
COLOR_BG_CARD        = "#1C2333"
COLOR_BORDER         = "#30363D"

COLOR_TEXT_PRIMARY   = "#E6EDF3"
COLOR_TEXT_SECONDARY = "#8B949E"
COLOR_TEXT_MUTED     = "#484F58"

COLOR_ACCENT         = "#58A6FF"
COLOR_PACCAR_BLUE    = "#003087"

COLOR_SUCCESS        = "#3FB950"
COLOR_WARNING        = "#D29922"
COLOR_DANGER         = "#F85149"


# --- Main application stylesheet ---
MAIN_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {COLOR_BG_DARK};
    color: {COLOR_TEXT_PRIMARY};
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
}}

QTabWidget::pane {{
    border: 1px solid {COLOR_BORDER};
    background-color: {COLOR_BG_PANEL};
}}

QTabBar::tab {{
    background-color: {COLOR_BG_DARK};
    color: {COLOR_TEXT_SECONDARY};
    padding: 8px 20px;
    border: 1px solid {COLOR_BORDER};
    border-bottom: none;
    margin-right: 2px;
    font-size: 12px;
    font-weight: 600;
}}

QTabBar::tab:selected {{
    background-color: {COLOR_BG_PANEL};
    color: {COLOR_TEXT_PRIMARY};
    border-top: 2px solid {COLOR_ACCENT};
}}

QTabBar::tab:hover:!selected {{
    background-color: {COLOR_BG_CARD};
    color: {COLOR_TEXT_PRIMARY};
}}

QFrame#card {{
    background-color: {COLOR_BG_CARD};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}

QPushButton {{
    background-color: {COLOR_BG_CARD};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER};
    border-radius: 5px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {COLOR_ACCENT};
    color: {COLOR_BG_DARK};
    border-color: {COLOR_ACCENT};
}}

QPushButton:pressed {{
    background-color: #1f6feb;
}}

QPushButton:disabled {{
    color: {COLOR_TEXT_MUTED};
    border-color: {COLOR_BORDER};
}}

QPushButton#btn_danger {{
    border-color: {COLOR_DANGER};
    color: {COLOR_DANGER};
}}

QPushButton#btn_danger:hover {{
    background-color: {COLOR_DANGER};
    color: white;
}}

QPushButton#btn_success {{
    border-color: {COLOR_SUCCESS};
    color: {COLOR_SUCCESS};
}}

QPushButton#btn_success:hover {{
    background-color: {COLOR_SUCCESS};
    color: {COLOR_BG_DARK};
}}

QComboBox {{
    background-color: {COLOR_BG_CARD};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER};
    border-radius: 5px;
    padding: 4px 8px;
    font-size: 12px;
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background-color: {COLOR_BG_CARD};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER};
    selection-background-color: {COLOR_ACCENT};
    selection-color: {COLOR_BG_DARK};
}}

QScrollBar:vertical {{
    background-color: {COLOR_BG_DARK};
    width: 8px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background-color: {COLOR_BORDER};
    border-radius: 4px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {COLOR_TEXT_MUTED};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QTextEdit {{
    background-color: {COLOR_BG_DARK};
    color: {COLOR_TEXT_SECONDARY};
    border: 1px solid {COLOR_BORDER};
    border-radius: 5px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 11px;
    padding: 6px;
}}

QProgressBar {{
    background-color: {COLOR_BG_DARK};
    border: none;
    border-radius: 3px;
}}

QProgressBar::chunk {{
    background-color: {COLOR_ACCENT};
    border-radius: 3px;
}}

QStatusBar {{
    background-color: {COLOR_BG_CARD};
    color: {COLOR_TEXT_SECONDARY};
    border-top: 1px solid {COLOR_BORDER};
    font-size: 11px;
}}

QLabel {{
    background-color: transparent;
}}

QSplitter::handle {{
    background-color: {COLOR_BORDER};
}}
"""
