"""Dark theme for the Qt GUI."""
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication

ACCENT = "#ff7a18"
BG = "#15171c"
PANEL = "#1d2027"
CARD = "#252932"
BORDER = "#323743"
TEXT = "#e6e8ee"
MUTED = "#8b93a5"

# series colours (also used for markers on the image)
COLORS = {
    "max": "#ff4d4f",
    "min": "#3fa7ff",
    "center": "#52d273",
    "mean": "#c0c4cc",
    "roi_max": "#ffd43b",
    "roi_min": "#9ad0ff",
    "roi_mean": "#e6e089",
    "P1": "#ffb020",
    "P2": "#d66efd",
    "P3": "#20e3c2",
    "P4": "#ff6fb5",
    "P5": "#a3e635",
    "P6": "#7c8cff",
    "cam1": "#f1f3f5",
    "cam2": "#ffc9a3",
    "cam3": "#b2f2bb",
}

STYLE = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-size: 10pt; }}
QMainWindow::separator {{ background: {BORDER}; width: 1px; height: 1px; }}
QToolBar {{ background: {PANEL}; border: none; border-bottom: 1px solid {BORDER}; padding: 4px; spacing: 6px; }}
QToolBar QToolButton {{ padding: 5px 10px; border-radius: 6px; }}
QToolBar QToolButton:hover {{ background: {CARD}; }}
QToolBar QToolButton:checked {{ background: {ACCENT}; color: #111; }}
QStatusBar {{ background: {PANEL}; color: {MUTED}; border-top: 1px solid {BORDER}; }}
QFrame#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; }}
QLabel#CardTitle {{ color: {MUTED}; font-size: 8.5pt; background: transparent; }}
QLabel#CardValue {{ font-size: 18pt; font-weight: 600; background: transparent; }}
QLabel#CardSub {{ color: {MUTED}; font-size: 8pt; background: transparent; }}
QLabel#Hint {{ color: {MUTED}; font-size: 8.5pt; }}
QLabel#Section {{ color: {ACCENT}; font-weight: 600; padding-top: 6px; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; top: -1px; background: {PANEL}; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 7px 12px; border: none; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabWidget > QWidget > QWidget {{ background: {PANEL}; }}
QPushButton {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:checked {{ background: {ACCENT}; color: #111; border-color: {ACCENT}; }}
QPushButton:disabled {{ color: #555; }}
QPushButton#Primary {{ background: {ACCENT}; color: #111; font-weight: 600; border: none; }}
QPushButton#Danger {{ background: #e5484d; color: white; font-weight: 600; border: none; }}
QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit {{ background: {CARD}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 4px 8px; min-height: 20px; }}
QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{ background: {CARD}; selection-background-color: {ACCENT}; selection-color: #111; }}
QCheckBox, QRadioButton {{ background: transparent; spacing: 6px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
QListWidget, QTableWidget {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}
QHeaderView::section {{ background: {PANEL}; color: {MUTED}; border: none; padding: 4px; }}
QTableWidget {{ gridline-color: {BORDER}; }}
QScrollArea {{ border: none; }}
QSplitter::handle {{ background: {BORDER}; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER}; }}
QFrame#Header {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
QLabel#AppTitle {{ font-size: 12pt; font-weight: 700; background: transparent; }}
QLabel#AppSub {{ color: {MUTED}; font-size: 8.5pt; background: transparent; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 7px; padding: 5px 8px; }}
QToolButton:hover {{ background: {CARD}; border-color: {BORDER}; }}
QToolButton:checked {{ background: {CARD}; border-color: {ACCENT}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QFrame#Segmented {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 9px; }}
QFrame#Segmented QToolButton {{ border-radius: 7px; padding: 4px 10px; color: {MUTED}; }}
QFrame#Segmented QToolButton:checked {{ background: {ACCENT}; color: #111; border-color: {ACCENT}; }}
QPushButton#Capture {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 17px; padding: 7px 16px;
    font-weight: 600; }}
QPushButton#Capture:hover {{ border-color: {ACCENT}; }}
QPushButton#RecOff {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 17px; padding: 7px 16px;
    font-weight: 600; }}
QPushButton#RecOff:hover {{ border-color: #ff4d4f; }}
QPushButton#RecOn {{ background: #e5484d; color: white; border: 1px solid #ff6b6f; border-radius: 17px;
    padding: 7px 16px; font-weight: 700; font-family: "Segoe UI", "Consolas"; }}
QPushButton#Folder {{ background: transparent; border: 1px dashed {BORDER}; border-radius: 17px; padding: 6px 12px;
    color: {MUTED}; text-align: left; }}
QPushButton#Folder:hover {{ border-color: {ACCENT}; color: {TEXT}; }}
QLabel#CardValueSmall {{ font-size: 12pt; font-weight: 600; background: transparent; }}
QLabel#Pill {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 11px; padding: 3px 10px;
    color: {MUTED}; font-size: 8.5pt; }}
QLabel#PillRec {{ background: rgba(229,72,77,0.18); border: 1px solid #e5484d; border-radius: 11px;
    padding: 3px 10px; color: #ff8a8d; font-size: 8.5pt; font-weight: 600; }}
QFrame#Advanced {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#TrendBar {{ background: transparent; }}
"""


def apply(app: QApplication):
    app.setStyle("Fusion")
    pal = QPalette()
    for role, color in [
        (QPalette.ColorRole.Window, BG), (QPalette.ColorRole.WindowText, TEXT),
        (QPalette.ColorRole.Base, CARD), (QPalette.ColorRole.AlternateBase, PANEL),
        (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.Button, CARD),
        (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, ACCENT),
        (QPalette.ColorRole.HighlightedText, "#111111"), (QPalette.ColorRole.ToolTipBase, CARD),
        (QPalette.ColorRole.ToolTipText, TEXT),
    ]:
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    font = QFont("Segoe UI", 10)
    font.setFamilies(["Segoe UI", "Leelawadee UI", "Tahoma"])
    app.setFont(font)
    app.setStyleSheet(STYLE)
