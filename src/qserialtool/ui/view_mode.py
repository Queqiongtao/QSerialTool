"""分栏与终端视图的切换控制。"""

from PySide6.QtCore import QByteArray, QObject, Signal
from PySide6.QtWidgets import QSplitter, QWidget

from qserialtool.domain import ViewMode
from qserialtool.ui.receive_panel import ReceivePanel
from qserialtool.ui.send_panel import SendPanel


class ViewModeController(QObject):
    """管理分栏/终端视图切换与接收/发送分栏比例记忆。"""

    preferences_changed = Signal()
    mode_changed = Signal(str)

    def __init__(
        self,
        parent: QWidget,
        *,
        receive_panel: ReceivePanel,
        send_panel: SendPanel,
        splitter: QSplitter,
    ) -> None:
        super().__init__(parent)
        self._receive_panel = receive_panel
        self._send_panel = send_panel
        self._splitter = splitter
        self._mode: ViewMode = "split"
        self._split_view_state: QByteArray | None = None

    @property
    def mode(self) -> ViewMode:
        """返回当前视图模式。"""
        return self._mode

    def set_mode(self, mode: ViewMode, *, persist: bool = True) -> None:
        """在分栏视图与终端视图之间切换。"""
        if mode not in {"split", "terminal"}:
            return
        terminal = mode == "terminal"
        splitter = self._splitter
        if terminal and not self._send_panel.isHidden():
            self._split_view_state = splitter.saveState()
        self._mode = mode

        if terminal:
            if self._send_panel.periodic_button.isChecked():
                self._send_panel.periodic_button.setChecked(False)
            self._receive_panel.set_terminal_mode(True)
            self._send_panel.setVisible(False)
            splitter.setHandleWidth(0)
            splitter.handle(1).setEnabled(False)
            splitter.setSizes([max(splitter.height(), 1), 0])
            self._receive_panel.focus_terminal_input()
        else:
            self._receive_panel.set_terminal_mode(False)
            self._send_panel.setVisible(True)
            splitter.setHandleWidth(6)
            splitter.handle(1).setEnabled(True)
            if self._split_view_state is not None:
                splitter.restoreState(self._split_view_state)
            else:
                reference = max(splitter.height(), 400)
                splitter.setSizes([reference * 3 // 4, max(120, reference // 4)])
            self._send_panel.editor.setFocus()

        self.mode_changed.emit(mode)
        if persist:
            self.preferences_changed.emit()

    def apply_split_state(self, state: QByteArray) -> None:
        """恢复接收/发送分栏比例：分栏视图立即应用，终端视图暂存待切回时恢复。"""
        if self._mode == "split":
            self._splitter.restoreState(state)
        else:
            self._split_view_state = state

    def split_state_base64(self) -> str:
        """返回可持久化的接收/发送分栏比例；终端视图下返回最近一次分栏比例。"""
        if self._mode == "terminal" and self._split_view_state is not None:
            state = self._split_view_state
        else:
            state = self._splitter.saveState()
        return bytes(state.toBase64()).decode("ascii")
