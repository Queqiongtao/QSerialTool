"""主窗口头部控件构建、字号档位与外观应用。"""

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QTabWidget,
    QToolButton,
    QWidget,
)

from qserialtool.domain import Theme
from qserialtool.ui.session_tab import SessionTab
from qserialtool.ui.theme_manager import (
    DATA_FONT_PRESETS,
    HEADER_BUTTON_SIZE_PX,
    data_font,
)

# “主题”子菜单的显示标签与配置值。
THEMES: tuple[tuple[str, Theme], ...] = (
    ("跟随系统", "system"),
    ("浅色", "light"),
    ("深色", "dark"),
)

# “字号”子菜单的档位选项：0 表示跟随系统。
FONT_SIZE_CHOICES: tuple[tuple[str, int], ...] = (
    ("跟随系统", 0),
    *((str(size), size) for size in DATA_FONT_PRESETS),
)


@dataclass(frozen=True, slots=True)
class MainActionCallbacks:
    """构建头部动作所需的主窗口回调。"""

    new_session: Callable[[], None]
    close_current: Callable[[], None]
    clear_current: Callable[[], None]
    zoom_font: Callable[[int], None]
    reset_font_size: Callable[[], None]
    show_help: Callable[[], None]
    show_about: Callable[[], None]
    font_size_changed: Callable[[int], None]
    theme_changed: Callable[[Theme], None]


@dataclass(frozen=True, slots=True)
class MainActions:
    """主窗口头部的构建结果：菜单、按钮与动作。"""

    main_menu: QMenu
    menu_button: QToolButton
    header_tools: QWidget
    theme_menu: QMenu
    theme_actions: tuple[QAction, ...]
    font_menu: QMenu
    font_size_actions: tuple[QAction, ...]
    font_zoom_in_action: QAction
    font_zoom_out_action: QAction
    font_reset_action: QAction
    help_action: QAction
    about_action: QAction
    clear_action: QAction


@dataclass(frozen=True, slots=True)
class _FontActions:
    """字号子菜单、档位动作与缩放动作。"""

    menu: QMenu
    size_actions: tuple[QAction, ...]
    zoom_in: QAction
    zoom_out: QAction
    reset: QAction


def build_main_actions(
    window: QMainWindow,
    tabs: QTabWidget,
    *,
    theme: Theme,
    data_font_size: int,
    callbacks: MainActionCallbacks,
) -> MainActions:
    """构建“☰”菜单（含主题/字号可勾选子菜单）和标签栏角落控件。

    去掉菜单栏和工具栏后，动作必须用 ``window.addAction()`` 挂到窗口，
    快捷键才会继续生效。
    """
    new_action = QAction("新建会话", window)
    new_action.setShortcut("Ctrl+T")
    new_action.triggered.connect(callbacks.new_session)
    close_action = QAction("关闭当前会话", window)
    close_action.setShortcut("Ctrl+W")
    close_action.triggered.connect(callbacks.close_current)
    clear_action = QAction("清空接收区", window)
    clear_action.setShortcut("Ctrl+L")
    clear_action.triggered.connect(callbacks.clear_current)
    exit_action = QAction("退出", window)
    exit_action.setShortcut("Ctrl+Q")
    exit_action.triggered.connect(window.close)

    font_actions = _build_font_menu(window, data_font_size, callbacks)
    theme_menu, theme_actions = _build_theme_menu(window, theme, callbacks.theme_changed)
    help_action = QAction("使用帮助", window)
    help_action.setShortcut(QKeySequence("F1"))
    help_action.triggered.connect(callbacks.show_help)
    about_action = QAction("关于 QSerialTool", window)
    about_action.triggered.connect(callbacks.show_about)

    main_menu = QMenu(window)
    main_menu.addAction(new_action)
    main_menu.addAction(close_action)
    main_menu.addAction(clear_action)
    main_menu.addSeparator()
    main_menu.addMenu(theme_menu)
    main_menu.addMenu(font_actions.menu)
    main_menu.addSeparator()
    main_menu.addAction(help_action)
    main_menu.addAction(about_action)
    main_menu.addSeparator()
    main_menu.addAction(exit_action)
    for action in (
        new_action,
        close_action,
        clear_action,
        exit_action,
        help_action,
        font_actions.zoom_in,
        font_actions.zoom_out,
        font_actions.reset,
    ):
        window.addAction(action)

    menu_button = _build_menu_button(window, main_menu)

    tabs.setDocumentMode(True)
    header_tools = _install_header_tools(window, menu_button=menu_button)
    tabs.setCornerWidget(header_tools, Qt.Corner.TopRightCorner)
    # 设置角落控件会重新挂载父级并隐藏控件，必须显式显示。
    header_tools.show()
    tabs.tabBar().installEventFilter(window)

    return MainActions(
        main_menu=main_menu,
        menu_button=menu_button,
        header_tools=header_tools,
        theme_menu=theme_menu,
        theme_actions=theme_actions,
        font_menu=font_actions.menu,
        font_size_actions=font_actions.size_actions,
        font_zoom_in_action=font_actions.zoom_in,
        font_zoom_out_action=font_actions.zoom_out,
        font_reset_action=font_actions.reset,
        help_action=help_action,
        about_action=about_action,
        clear_action=clear_action,
    )


def _build_menu_button(window: QWidget, menu: QMenu) -> QToolButton:
    """构造“☰”菜单按钮，固定为与标签栏“+”同高的方形。"""
    button = QToolButton(window)
    button.setText("☰")
    button.setAutoRaise(True)
    button.setFixedSize(HEADER_BUTTON_SIZE_PX, HEADER_BUTTON_SIZE_PX)
    button.setToolTip("新建会话 / 关闭当前会话 / 清空接收区 / 主题 / 字号 / 使用帮助 / 关于 / 退出")
    button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    button.setMenu(menu)
    return button


def _install_header_tools(window: QWidget, *, menu_button: QToolButton) -> QWidget:
    """把“☰”按钮装配成标签栏右上角控件。"""
    header_tools = QWidget(window)
    header_tools.setObjectName("headerTools")
    layout = QHBoxLayout(header_tools)
    layout.setContentsMargins(2, 0, 4, 0)
    layout.setSpacing(4)
    layout.addWidget(menu_button)
    return header_tools


def _build_font_menu(
    window: QWidget,
    data_font_size: int,
    callbacks: MainActionCallbacks,
) -> _FontActions:
    """构造“字号”子菜单：档位勾选列表加放大/缩小/恢复默认。"""
    menu = QMenu("字号", window)
    group = QActionGroup(window)
    group.setExclusive(True)
    size_actions: list[QAction] = []
    for label, value in FONT_SIZE_CHOICES:
        action = _build_choice_action(
            window, label, value, value == data_font_size, callbacks.font_size_changed
        )
        group.addAction(action)
        menu.addAction(action)
        size_actions.append(action)
    menu.addSeparator()
    zoom_in = QAction("放大", window)
    zoom_in.setShortcuts([QKeySequence("Ctrl+="), QKeySequence("Ctrl++")])
    zoom_in.triggered.connect(lambda: callbacks.zoom_font(1))
    zoom_out = QAction("缩小", window)
    zoom_out.setShortcut("Ctrl+-")
    zoom_out.triggered.connect(lambda: callbacks.zoom_font(-1))
    reset = QAction("恢复默认", window)
    reset.setShortcut("Ctrl+0")
    reset.triggered.connect(callbacks.reset_font_size)
    menu.addAction(zoom_in)
    menu.addAction(zoom_out)
    menu.addAction(reset)
    return _FontActions(
        menu=menu,
        size_actions=tuple(size_actions),
        zoom_in=zoom_in,
        zoom_out=zoom_out,
        reset=reset,
    )


def _build_theme_menu(
    window: QWidget,
    theme: Theme,
    on_selected: Callable[[object], None],
) -> tuple[QMenu, tuple[QAction, ...]]:
    """构造“主题”子菜单，三个选项互斥，勾选即切换。"""
    menu = QMenu("主题", window)
    group = QActionGroup(window)
    group.setExclusive(True)
    actions: list[QAction] = []
    for label, value in THEMES:
        action = _build_choice_action(window, label, value, value == theme, on_selected)
        group.addAction(action)
        menu.addAction(action)
        actions.append(action)
    return menu, tuple(actions)


def _build_choice_action(
    window: QWidget,
    label: str,
    value: object,
    checked: bool,
    on_selected: Callable[[object], None],
) -> QAction:
    """构造可勾选单选动作，勾选时把对应配置值回传给回调。"""
    action = QAction(label, window)
    action.setCheckable(True)
    action.setData(value)
    action.setChecked(checked)

    def _handle(selected: bool) -> None:
        if selected:
            on_selected(value)

    action.toggled.connect(_handle)
    return action


def next_font_size(current_data: object, step: int) -> int:
    """按预设档位返回下一个字号；跟随系统时以系统字号为基准。"""
    if isinstance(current_data, int) and current_data > 0:
        effective = current_data
    else:
        system_size = data_font().pointSize()
        effective = system_size if system_size > 0 else DATA_FONT_PRESETS[0]
    if step > 0:
        candidates = [value for value in DATA_FONT_PRESETS if value > effective]
        return candidates[0] if candidates else DATA_FONT_PRESETS[-1]
    candidates = [value for value in DATA_FONT_PRESETS if value < effective]
    return candidates[-1] if candidates else DATA_FONT_PRESETS[0]


def show_and_raise(current: QWidget | None, factory: Callable[[], QWidget]) -> QWidget:
    """惰性创建窗口并置前激活，返回复用或新建的窗口。"""
    widget = current if current is not None else factory()
    widget.show()
    widget.raise_()
    widget.activateWindow()
    return widget


def apply_data_font_size(tabs: QTabWidget, size: int) -> None:
    """对全部会话标签应用数据区字号。"""
    for index in range(tabs.count()):
        widget = tabs.widget(index)
        if isinstance(widget, SessionTab):
            widget.set_data_font_size(size)


def refresh_session_tabs(tabs: QTabWidget, data_font_size: int) -> None:
    """主题切换后重设数据区字号并刷新配色。

    ``apply_theme()`` 重新应用样式表会重置数据区字体，因此必须补一次字号。
    """
    for index in range(tabs.count()):
        widget = tabs.widget(index)
        if isinstance(widget, SessionTab):
            widget.set_data_font_size(data_font_size)
            widget.refresh_theme()
