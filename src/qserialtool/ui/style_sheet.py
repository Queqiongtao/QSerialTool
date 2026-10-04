"""浅色与深色主题的设计令牌和全局 QSS 样式表。

令牌是颜色的唯一来源：``apply_theme()`` 同时用它设置调色板和样式表，两者必须保持
一致，否则 palette 对比度测试将不再反映真实渲染结果。样式表刻意不声明任何字体属性，
数据区的等宽字体由 ``data_font()`` 在控件上单独设置。
"""

import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    """一套主题下的界面颜色令牌。"""

    window: str
    surface: str
    subtle: str
    editor: str
    input: str
    border: str
    border_strong: str
    text: str
    muted: str
    accent: str
    accent_fill: str
    accent_fill_hover: str
    accent_fill_pressed: str
    accent_soft: str


_TOKENS: dict[str, ThemeTokens] = {
    "light": ThemeTokens(
        window="#F3F4F6",
        surface="#FFFFFF",
        subtle="#F9FAFB",
        editor="#FFFFFF",
        input="#FFFFFF",
        border="#D8DCE3",
        border_strong="#C2C8D2",
        text="#1F2328",
        muted="#6B7280",
        accent="#2563EB",
        accent_fill="#2563EB",
        accent_fill_hover="#1D4ED8",
        accent_fill_pressed="#1E40AF",
        accent_soft="#EAF0FE",
    ),
    "dark": ThemeTokens(
        window="#1B1D21",
        surface="#232629",
        subtle="#2A2E33",
        editor="#17191C",
        input="#2A2E33",
        border="#34383E",
        border_strong="#454B54",
        text="#E6E8EB",
        muted="#9AA1AA",
        # 深色下强调色分两类：文字/边框用亮蓝保证对比度，实心按钮底用深蓝保证白字可读。
        accent="#6BA1FF",
        accent_fill="#2563EB",
        accent_fill_hover="#3B82F6",
        accent_fill_pressed="#1D4ED8",
        accent_soft="#1E2A3D",
    ),
}


def tokens(theme_name: str) -> ThemeTokens:
    """返回指定主题的颜色令牌。"""
    return _TOKENS[theme_name]


def assets_dir() -> Path:
    """返回样式资源目录；PyInstaller 单文件模式下指向解包目录。"""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "qserialtool" / "ui" / "assets"
    return Path(__file__).resolve().parent / "assets"


def build_stylesheet(theme_name: str) -> str:
    """按主题令牌生成全局 QSS。"""
    c = tokens(theme_name)
    assets = assets_dir().as_posix()
    return f"""
QMainWindow, QDialog {{
    background: {c.window};
    color: {c.text};
}}
QLabel {{
    color: {c.text};
    background: transparent;
}}
QLabel#panelHeading {{
    color: {c.text};
    font-weight: 600;
}}
QLabel#statusText {{
    color: {c.muted};
    background: transparent;
}}
QFrame#statusFrame {{
    background: {c.subtle};
    border: none;
    border-top: 1px solid {c.border};
}}

QTabWidget::pane {{
    border: none;
    background: {c.window};
}}
QTabBar {{
    qproperty-drawBase: 0;
}}
QTabBar::tab {{
    background: transparent;
    color: {c.muted};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 6px 14px;
    margin-right: 2px;
}}
QTabBar::tab:hover:!selected {{
    color: {c.text};
    background: {c.subtle};
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{
    color: {c.text};
    background: {c.surface};
    border-bottom: 2px solid {c.accent};
}}

QGroupBox {{
    background: {c.surface};
    border: 1px solid {c.border};
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px 10px 10px 10px;
    color: {c.text};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 4px;
    color: {c.muted};
    font-weight: 600;
}}

QComboBox, QLineEdit, QSpinBox, QAbstractSpinBox {{
    background: {c.input};
    color: {c.text};
    border: 1px solid {c.border};
    border-radius: 6px;
    padding: 2px 8px;
    selection-background-color: {c.accent_fill};
    selection-color: #FFFFFF;
}}
QComboBox:hover, QLineEdit:hover, QSpinBox:hover, QAbstractSpinBox:hover {{
    border-color: {c.border_strong};
}}
QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QAbstractSpinBox:focus {{
    border-color: {c.accent};
}}
QComboBox:disabled, QLineEdit:disabled, QSpinBox:disabled, QAbstractSpinBox:disabled {{
    background: {c.subtle};
    color: {c.muted};
    border-color: {c.border};
}}
QComboBox QLineEdit {{
    border: none;
    border-radius: 0;
    padding: 0;
    background: transparent;
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    border: none;
    background: transparent;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: url("{assets}/chevron-down.svg");
    width: 11px;
    height: 11px;
}}
QComboBox::down-arrow:disabled {{
    image: url("{assets}/chevron-down-disabled.svg");
    width: 11px;
    height: 11px;
}}
QComboBox QAbstractItemView {{
    background: {c.surface};
    color: {c.text};
    border: 1px solid {c.border};
    border-radius: 6px;
    padding: 4px;
    outline: none;
    selection-background-color: {c.accent_fill};
    selection-color: #FFFFFF;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    subcontrol-origin: border;
    background: transparent;
    border: none;
    width: 18px;
}}
QSpinBox::up-button {{
    subcontrol-position: top right;
}}
QSpinBox::down-button {{
    subcontrol-position: bottom right;
}}
QSpinBox::up-arrow {{
    image: url("{assets}/chevron-up.svg");
    width: 9px;
    height: 9px;
}}
QSpinBox::down-arrow {{
    image: url("{assets}/chevron-down.svg");
    width: 9px;
    height: 9px;
}}

QPushButton {{
    background: {c.surface};
    color: {c.text};
    border: 1px solid {c.border};
    border-radius: 6px;
    padding: 3px 10px;
}}
QPushButton:hover {{
    background: {c.subtle};
    border-color: {c.border_strong};
}}
QPushButton:pressed {{
    background: {c.accent_soft};
    border-color: {c.border_strong};
}}
QPushButton:checked {{
    background: {c.accent_soft};
    border-color: {c.accent};
    color: {c.accent};
}}
QPushButton:disabled {{
    background: {c.subtle};
    color: {c.muted};
    border-color: {c.border};
}}
QPushButton[primary="true"] {{
    background: {c.accent_fill};
    color: #FFFFFF;
    border: 1px solid {c.accent_fill};
    font-weight: 600;
    padding: 3px 12px;
}}
QPushButton[primary="true"]:hover {{
    background: {c.accent_fill_hover};
    border-color: {c.accent_fill_hover};
}}
QPushButton[primary="true"]:pressed {{
    background: {c.accent_fill_pressed};
    border-color: {c.accent_fill_pressed};
}}
QPushButton[primary="true"]:disabled {{
    background: {c.border};
    color: {c.muted};
    border-color: {c.border};
}}

QToolButton {{
    background: transparent;
    color: {c.muted};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 2px 7px;
}}
QToolButton:hover {{
    background: {c.subtle};
    border-color: {c.border};
    color: {c.text};
}}
QToolButton:pressed {{
    background: {c.accent_soft};
}}
QToolButton:checked {{
    background: {c.accent_soft};
    border-color: {c.accent};
    color: {c.accent};
}}
QToolButton:disabled {{
    color: {c.muted};
    background: transparent;
}}
QToolButton::menu-indicator {{
    image: none;
}}

QCheckBox {{
    color: {c.text};
    background: transparent;
    spacing: 6px;
}}
QCheckBox:disabled {{
    color: {c.muted};
}}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {c.border_strong};
    border-radius: 4px;
    background: {c.input};
}}
QCheckBox::indicator:hover {{
    border-color: {c.accent};
}}
QCheckBox::indicator:checked {{
    background: {c.accent_fill};
    border-color: {c.accent_fill};
    image: url("{assets}/check.svg");
}}
QCheckBox::indicator:disabled {{
    background: {c.subtle};
    border-color: {c.border};
}}
QCheckBox::indicator:checked:disabled {{
    background: {c.subtle};
    border-color: {c.border_strong};
    image: url("{assets}/check-disabled.svg");
}}

QPlainTextEdit, QTextEdit {{
    background: {c.editor};
    color: {c.text};
    border: 1px solid {c.border};
    border-radius: 6px;
    padding: 4px;
}}
QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {c.accent};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {c.border_strong};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c.muted};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {c.border_strong};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {c.muted};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
    background: transparent;
    border: none;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

QSplitter::handle {{
    background: transparent;
}}
QSplitter::handle:hover {{
    background: {c.accent_soft};
}}

QMenu {{
    background: {c.surface};
    color: {c.text};
    border: 1px solid {c.border};
    padding: 4px;
}}
QMenu::item {{
    padding: 5px 20px 5px 12px;
    border-radius: 5px;
}}
QMenu::item:selected {{
    background: {c.accent_fill};
    color: #FFFFFF;
}}
QMenu::item:disabled {{
    color: {c.muted};
}}
QMenu::separator {{
    height: 1px;
    background: {c.border};
    margin: 4px 8px;
}}

QToolTip {{
    background: {c.surface};
    color: {c.text};
    border: 1px solid {c.border};
    padding: 4px;
}}
""".strip()
