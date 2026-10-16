"""全局 QSS 样式表模板，占位符由主题令牌与资源目录填充。"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .style_sheet import ThemeTokens


def render_qss(colors: "ThemeTokens", assets: str) -> str:
    """按令牌值与资源目录渲染全局 QSS 模板。"""
    c = colors
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
/* 接收区居中空态提示（ReceivePanel 的 empty_state 覆盖标签）。 */
QLabel#emptyState {{
    color: {c.muted};
    background: transparent;
}}
/* 标签栏右上角“☰”与窗口按钮所在容器。 */
QWidget#headerTools {{
    background: transparent;
}}
/* 标题行窗口按钮：贴近系统标题栏的方角悬停；关闭按钮悬停为 Fluent 红底反白。 */
QWidget#windowControls {{
    background: transparent;
}}
QToolButton#windowMinButton, QToolButton#windowMaxButton, QToolButton#windowCloseButton {{
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
}}
QToolButton#windowMinButton:hover, QToolButton#windowMaxButton:hover {{
    background: {c.border};
}}
QToolButton#windowMinButton:pressed, QToolButton#windowMaxButton:pressed {{
    background: {c.border_strong};
}}
QToolButton#windowCloseButton {{
    image: url("{assets}/window-close.svg");
}}
QToolButton#windowCloseButton:hover, QToolButton#windowCloseButton:pressed {{
    background: #C42B1C;
    image: url("{assets}/window-close-active.svg");
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
/* 标签关闭按钮：中性灰，悬停变强调蓝提示可点击。 */
QTabBar::close-button {{
    image: url("{assets}/close.svg");
    width: 12px;
    height: 12px;
}}
QTabBar::close-button:hover {{
    image: url("{assets}/close-hover.svg");
}}
/* 侧栏面板化：整列浅色底 + 右侧分隔线，卡片浮在面板上。 */
QScrollArea#sessionSidebar {{
    background: {c.subtle};
    border: none;
    border-right: 1px solid {c.border};
}}
QScrollArea#sessionSidebar > QWidget#qt_scrollarea_viewport {{
    background: {c.subtle};
}}
QScrollArea#sessionSidebar > QWidget > QWidget {{
    background: {c.subtle};
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
/* 标签栏“+”新建按钮：实心强调色，与“连接”“发送”等主操作按钮一致。 */
QToolButton#newTabButton {{
    background: {c.accent_fill};
    border: 1px solid {c.accent_fill};
    border-radius: 6px;
    padding: 0;
}}
QToolButton#newTabButton:hover {{
    background: {c.accent_fill_hover};
    border-color: {c.accent_fill_hover};
}}
QToolButton#newTabButton:pressed {{
    background: {c.accent_fill_pressed};
    border-color: {c.accent_fill_pressed};
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
