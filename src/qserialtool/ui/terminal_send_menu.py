"""终端视图的“发送设置”菜单按钮。"""

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu, QToolButton, QWidget

from qserialtool.domain import DisplayMode, LineEnding


class TerminalSendMenu(QToolButton):
    """终端视图的发送设置按钮：格式、换行与发送历史。

    菜单只发出选择信号，不直接依赖发送或接收面板；由使用方把信号接到具体动作。
    """

    send_mode_selected = Signal(str)
    line_ending_selected = Signal(str)
    history_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText("发送设置")
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolTip("终端发送设置：格式、换行和历史")
        self.setVisible(False)

        menu = QMenu(self)
        self._format_actions: dict[DisplayMode, QAction] = {}
        format_menu = menu.addMenu("格式")
        format_group = QActionGroup(self)
        format_group.setExclusive(True)
        for label, value in (("文本", "text"), ("HEX", "hex")):
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked=False, value=value: self.send_mode_selected.emit(value)
            )
            format_group.addAction(action)
            format_menu.addAction(action)
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
        send_mode: DisplayMode,
        line_ending: LineEnding,
        history: tuple[str, ...],
    ) -> None:
        """让菜单反映当前发送偏好与发送历史。"""
        for value, action in self._format_actions.items():
            action.setChecked(value == send_mode)
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
