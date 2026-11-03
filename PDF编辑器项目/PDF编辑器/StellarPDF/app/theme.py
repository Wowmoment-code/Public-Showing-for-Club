"""Visual design tokens and Qt style sheet for Stellar PDF."""
from __future__ import annotations

from PySide6.QtGui import QColor


class C:
    """Colour palette inspired by modern Chinese office suites, but original."""

    PRIMARY = "#2F6BFF"
    PRIMARY_DARK = "#1F55D6"
    PRIMARY_LIGHT = "#EAF1FF"
    PRIMARY_SOFT = "#F3F7FF"
    ACCENT = "#6A4DFF"
    ACCENT_WARM = "#FF8A3D"
    SUCCESS = "#1FA971"
    WARNING = "#E8A317"
    DANGER = "#E5484D"
    TEXT = "#222633"
    TEXT_SUB = "#5E6678"
    TEXT_MUTED = "#8A91A1"
    BORDER = "#E3E7EE"
    BORDER_STRONG = "#D5DAE3"
    CANVAS = "#EEF1F6"
    PANEL = "#FFFFFF"
    RIBBON = "#F8F9FC"
    HOVER = "#EDF2FC"
    CHECKED = "#DFEAFF"
    SHADOW = "#C8CEDA"
    DARK = "#191C24"


def qcolor(value: str, alpha: int | None = None) -> QColor:
    color = QColor(value)
    if alpha is not None:
        color.setAlpha(alpha)
    return color


STYLESHEET = f"""
* {{
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
    font-size: 9.5pt;
    color: {C.TEXT};
    outline: none;
}}
QMainWindow, QDialog {{
    background: {C.PANEL};
}}
QWidget#RootWindow {{
    background: {C.PANEL};
}}
QWidget#TitleBar {{
    background: #FFFFFF;
    border-bottom: 1px solid {C.BORDER};
}}
QLabel#AppName {{
    color: {C.TEXT};
    font-size: 10pt;
    font-weight: 600;
}}
QLabel#DocTitle {{
    color: #3A4050;
    font-size: 9.5pt;
}}
QLabel#TitleMuted {{
    color: {C.TEXT_MUTED};
    font-size: 8.5pt;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 2px;
}}
QToolButton:hover {{
    background: {C.HOVER};
}}
QToolButton:pressed {{
    background: #DDE8FB;
}}
QToolButton:checked {{
    background: {C.CHECKED};
    border-color: #C9DBFF;
}}
QToolButton#WindowButton {{
    border-radius: 0;
    padding: 0;
}}
QToolButton#WindowButton:hover {{
    background: #EEF1F6;
}}
QToolButton#CloseButton {{
    border-radius: 0;
    padding: 0;
}}
QToolButton#CloseButton:hover {{
    background: #E5484D;
}}
QWidget#RibbonTabs {{
    background: #FFFFFF;
    border-bottom: 1px solid {C.BORDER};
}}
QTabBar#RibbonTabBar {{
    background: transparent;
}}
QTabBar#RibbonTabBar::tab {{
    background: transparent;
    color: #4A5164;
    padding: 7px 16px 8px 16px;
    margin: 0 1px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 9.5pt;
}}
QTabBar#RibbonTabBar::tab:hover {{
    color: {C.PRIMARY};
    background: {C.PRIMARY_SOFT};
}}
QTabBar#RibbonTabBar::tab:selected {{
    color: {C.PRIMARY};
    border-bottom: 2px solid {C.PRIMARY};
    font-weight: 600;
}}
QWidget#Ribbon {{
    background: {C.RIBBON};
    border-bottom: 1px solid {C.BORDER_STRONG};
}}
QFrame#RibbonSeparator {{
    background: {C.BORDER};
    max-width: 1px;
}}
QLabel#GroupLabel {{
    color: #8C93A3;
    font-size: 8pt;
}}
QToolButton#RibbonLarge {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 3px 7px 2px 7px;
    color: #333947;
    font-size: 8.6pt;
}}
QToolButton#RibbonLarge:hover {{
    background: #FFFFFF;
    border-color: #DCE5F5;
}}
QToolButton#RibbonLarge:pressed {{
    background: #E6EEFD;
}}
QToolButton#RibbonLarge:checked {{
    background: {C.PRIMARY_LIGHT};
    border-color: #C6D9FF;
}}
QToolButton#RibbonSmall {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 2px 6px 2px 3px;
    color: #3B4252;
    font-size: 8.6pt;
}}
QToolButton#RibbonSmall:hover {{
    background: #FFFFFF;
    border-color: #DCE5F5;
}}
QToolButton#RibbonSmall:pressed {{
    background: #E6EEFD;
}}
QToolButton#RibbonSmall:checked {{
    background: {C.PRIMARY_LIGHT};
    border-color: #C6D9FF;
}}
QToolButton#RibbonLarge::menu-indicator, QToolButton#RibbonSmall::menu-indicator {{
    image: none;
    width: 0px;
    height: 0px;
}}
QToolButton#RailButton {{
    border-radius: 8px;
    padding: 7px;
    margin: 2px 5px;
}}
QToolButton#RailButton:hover {{
    background: #F0F4FC;
}}
QToolButton#RailButton:checked {{
    background: {C.PRIMARY_LIGHT};
}}
QWidget#LeftRail {{
    background: #FBFCFE;
    border-right: 1px solid {C.BORDER};
}}
QWidget#SidePanel {{
    background: #FFFFFF;
    border-right: 1px solid {C.BORDER};
}}
QLabel#PanelTitle {{
    font-size: 10pt;
    font-weight: 600;
    color: #303645;
}}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: #FFFFFF;
    border: 1px solid {C.BORDER_STRONG};
    border-radius: 5px;
    padding: 5px 7px;
    selection-background-color: {C.PRIMARY};
    selection-color: white;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {C.PRIMARY};
}}
QLineEdit#TitleSearch {{
    background: #F3F5F9;
    border: 1px solid transparent;
    border-radius: 14px;
    padding: 5px 30px 5px 12px;
    color: #4A5164;
}}
QLineEdit#TitleSearch:focus {{
    background: #FFFFFF;
    border: 1px solid #C6D8FF;
}}
QPushButton {{
    background: #FFFFFF;
    border: 1px solid {C.BORDER_STRONG};
    border-radius: 5px;
    padding: 6px 15px;
    color: #333947;
}}
QPushButton:hover {{
    background: #F5F8FE;
    border-color: #BFD2FA;
}}
QPushButton:pressed {{
    background: #E9F0FE;
}}
QPushButton:disabled {{
    color: #B4BAC6;
    background: #F7F8FA;
    border-color: #E7EAF0;
}}
QPushButton#Primary {{
    background: {C.PRIMARY};
    border: 1px solid {C.PRIMARY};
    color: white;
    font-weight: 600;
    padding: 7px 20px;
}}
QPushButton#Primary:hover {{
    background: #3D77FF;
    border-color: #3D77FF;
}}
QPushButton#Primary:pressed {{
    background: {C.PRIMARY_DARK};
}}
QPushButton#Danger {{
    color: {C.DANGER};
    border-color: #F1C8CA;
}}
QPushButton#Danger:hover {{
    background: #FFF3F3;
}}
QPushButton#LinkButton {{
    border: none;
    background: transparent;
    color: {C.PRIMARY};
    padding: 2px 6px;
}}
QPushButton#LinkButton:hover {{
    background: {C.PRIMARY_LIGHT};
}}
QListWidget, QTreeWidget, QTableWidget {{
    background: #FFFFFF;
    border: none;
    outline: none;
}}
QListWidget::item {{
    border-radius: 5px;
    padding: 2px;
    color: #424958;
}}
QListWidget::item:hover {{
    background: #F5F8FE;
}}
QListWidget::item:selected {{
    background: {C.PRIMARY_LIGHT};
    color: #1F4FC4;
}}
QTreeWidget::item {{
    padding: 4px 2px;
    border-radius: 4px;
}}
QTreeWidget::item:hover {{
    background: #F5F8FE;
}}
QTreeWidget::item:selected {{
    background: {C.PRIMARY_LIGHT};
    color: #1F4FC4;
}}
QHeaderView::section {{
    background: #F7F9FC;
    border: none;
    border-bottom: 1px solid {C.BORDER};
    padding: 5px;
    color: #697184;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #C8CFDC;
    min-height: 30px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: #AEB7C7;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #C8CFDC;
    min-width: 30px;
    border-radius: 4px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}
QWidget#StatusBar {{
    background: #FFFFFF;
    border-top: 1px solid {C.BORDER};
}}
QLabel#StatusHint {{
    color: #7A8294;
    font-size: 8.5pt;
}}
QLabel#PageStatus {{
    color: #4E5667;
    font-size: 8.8pt;
}}
QSlider::groove:horizontal {{
    height: 3px;
    background: #DDE2EA;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {C.PRIMARY};
    width: 11px;
    height: 11px;
    margin: -4px 0;
    border-radius: 5px;
}}
QMenu {{
    background: #FFFFFF;
    border: 1px solid {C.BORDER_STRONG};
    border-radius: 6px;
    padding: 5px;
}}
QMenu::item {{
    padding: 6px 28px 6px 30px;
    border-radius: 4px;
    color: #3A4050;
}}
QMenu::item:selected {{
    background: {C.PRIMARY_LIGHT};
    color: {C.PRIMARY_DARK};
}}
QMenu::separator {{
    height: 1px;
    background: {C.BORDER};
    margin: 4px 7px;
}}
QToolTip {{
    background: #2A2F3A;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 5px 8px;
}}
QProgressBar {{
    border: 1px solid {C.BORDER};
    border-radius: 4px;
    background: #F2F4F8;
    text-align: center;
    color: #4C5465;
    height: 8px;
}}
QProgressBar::chunk {{
    background: {C.PRIMARY};
    border-radius: 3px;
}}
QTabWidget::pane {{
    border: 1px solid {C.BORDER};
    border-radius: 6px;
    background: white;
}}
QTabBar::tab {{
    background: transparent;
    padding: 7px 16px;
    color: #5C6474;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {C.PRIMARY};
    border-bottom: 2px solid {C.PRIMARY};
    font-weight: 600;
}}
QCheckBox, QRadioButton {{
    spacing: 7px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px;
    height: 15px;
}}
QCheckBox::indicator:unchecked {{
    border: 1px solid #B9C1CF;
    border-radius: 3px;
    background: white;
}}
QCheckBox::indicator:checked {{
    border: 1px solid {C.PRIMARY};
    border-radius: 3px;
    background: {C.PRIMARY};
}}
QSplitter::handle {{
    background: transparent;
}}
QFrame#Card {{
    background: #FFFFFF;
    border: 1px solid {C.BORDER};
    border-radius: 10px;
}}
QFrame#WelcomeCard {{
    background: #FFFFFF;
    border: 1px solid #E5EAF3;
    border-radius: 12px;
}}
QLabel#WelcomeTitle {{
    font-size: 25pt;
    font-weight: 700;
    color: #1E2638;
}}
QLabel#WelcomeSub {{
    font-size: 11pt;
    color: #6E778B;
}}
QLabel#SectionTitle {{
    font-size: 12pt;
    font-weight: 600;
    color: #2A3040;
}}
QLabel#Muted {{
    color: {C.TEXT_MUTED};
}}
QLabel#Badge {{
    background: #EAF1FF;
    color: {C.PRIMARY};
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 8pt;
}}
QProgressDialog {{
    background: white;
}}
"""
