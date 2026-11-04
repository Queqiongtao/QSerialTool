"""终端视图的“发送设置”菜单按钮。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu, QToolButton, QWidget

from qserialtool.domain import DisplayMode, LineEnding, TerminalInputMode
from qserialtool.ui.icons import set_action_icon


class TerminalSendMenu(QToolButton):
    """终端视图的发送设置按钮：输入方式、格式、换行与发送历史。

    菜单只发出选择信号，不直接依赖发送或接收面板；由使用方把信号接到具体动作。
    """

    input_mode_selected = Signal(str)
    send_mode_selected = Signal(str)
    line_ending_selected = Signal(str)
    history_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText("发送设置")
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        set_action_icon(self, "sliders")
        # QToolButton 默认只显示图标；这里需要“图标 + 文字”的普通按钮外观。
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setToolTip("终端发送设置：输入方式、格式、换行和历史")

        menu = QMenu(self)
        self._input_actions: dict[TerminalInputMode, QAction] = {}
        input_menu = menu.addMenu("输入")
        input_group = QActionGroup(self)
        input_group.setExclusive(True)
        for label, value, tooltip in (
            ("行缓冲（回车整行发送）", "line", "本地编辑，按回车后整行发送"),
            ("逐键发送（原始终端）", "raw", "按键立即发送，适合 Linux shell 的 Tab 补全"),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setToolTip(tooltip)
            action.triggered.connect(
                lambda _checked=False, value=value: self.input_mode_selected.emit(value)
            )
            input_group.addAction(action)
            input_menu.addAction(action)
            self._input_actions[value] = action

        self._format_actions: dict[DisplayMode, QAction] = {}
        self.format_menu = menu.addMenu("格式")
        self.format_menu.setToolTip("逐键模式按文本编码发送，HEX 仅用于行缓冲和分栏视图")
        format_group = QActionGroup(self)
        format_group.setExclusive(True)
        for label, value in (("文本", "text"), ("HEX", "hex")):
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked=False, value=value: self.send_mode_selected.emit(value)
            )
            format_group.addAction(action)
            self.format_menu.addAction(action)
            self._format_actions[value] = action

        self._newline_actions: dict[LineEnding, QAction] = {}
        newline_menu = menu.addMenu("换行")
        newline_group = QActionGroup(self)
        newline_group.setExclusive(True)
        for label, value in (
            ("无换行", "none"),
            ("CR", "cr"),
            ("LF", "lf"),
            ("CRLF", "crlf"),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked=False, value=value: self.line_ending_selected.emit(value)
            )
            newline_group.addAction(action)
            newline_menu.addAction(action)
            self._newline_actions[value] = action

        self.history_menu = menu.addMenu("历史")
        self.setMenu(menu)

    def sync(
        self,
        *,
        input_mode: TerminalInputMode,
        send_mode: DisplayMode,
        line_ending: LineEnding,
        history: tuple[str, ...],
    ) -> None:
        """让菜单反映当前输入方式、发送偏好与发送历史。

        逐键模式按文本发送，格式菜单固定显示“文本”并禁用；这里只影响菜单
        显示，不改写分栏视图保存的 HEX 发送格式。
        """
        for value, action in self._input_actions.items():
            action.setChecked(value == input_mode)
        effective_send_mode = "text" if input_mode == "raw" else send_mode
        for value, action in self._format_actions.items():
            action.setChecked(value == effective_send_mode)
        self.format_menu.setEnabled(input_mode == "line")
        for value, action in self._newline_actions.items():
            action.setChecked(value == line_ending)

        self.history_menu.clear()
        if not history:
            action = self.history_menu.addAction("暂无历史")
            action.setEnabled(False)
            return
        for item in reversed(history[-20:]):
            display = item.replace("\n", "\\n")[:80] or "(空)"
            action = self.history_menu.addAction(display)
            action.triggered.connect(
                lambda _checked=False, value=item: self.history_selected.emit(value)
            )
