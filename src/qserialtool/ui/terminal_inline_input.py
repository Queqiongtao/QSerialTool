"""终端模式输入控制：行缓冲草稿、逐键发送、历史、提交与粘贴。"""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

from qserialtool.domain import TerminalInputMode
from qserialtool.ui.terminal_keymap import raw_key_input


class TerminalInlineInput:
    """维护终端输入：行缓冲草稿或逐键发送两种模式。

    ``after_edit`` 在草稿写入文档后调用（宿主用于滚动视图）；``is_ready``
    返回宿主是否已渲染过至少一帧画面，未就绪时只记录草稿文本。行缓冲模式
    下普通 ``↑``/``↓`` 经 ``raw_send`` 原样透传给设备，``Shift+↑``/``Shift+↓``
    召回草稿历史；逐键模式不维护草稿，所有按键由 ``text_send``/``raw_send``
    立即发往设备。
    """

    def __init__(
        self,
        view: QPlainTextEdit,
        *,
        after_edit: Callable[[], None],
        is_ready: Callable[[], bool],
    ) -> None:
        self._view = view
        self._after_edit = after_edit
        self._is_ready = is_ready
        self._enabled = False
        self._mode: TerminalInputMode = "line"
        self._draft = ""
        self._input_start_position = 0
        self._cursor_block_number = 0
        self._history_index: int | None = None
        self._history_provider: Callable[[], tuple[str, ...]] = lambda: ()
        self._submit_handler: Callable[[str], bool] | None = None
        self._text_send: Callable[[str], bool] | None = None
        self._raw_send: Callable[[bytes], bool] | None = None

    @property
    def draft(self) -> str:
        """返回当前终端输入草稿；逐键模式始终为空。"""
        return self._draft

    @property
    def mode(self) -> TerminalInputMode:
        """返回当前输入模式。"""
        return self._mode

    @property
    def is_raw(self) -> bool:
        """返回是否处于逐键发送模式。"""
        return self._mode == "raw"

    def set_mode(self, mode: TerminalInputMode) -> None:
        """切换行缓冲/逐键模式，并丢弃尚未发送的本地草稿。"""
        if mode not in {"line", "raw"}:
            raise ValueError(f"不支持的终端输入模式：{mode}")
        if mode == self._mode:
            return
        if self._mode == "line":
            # 先移除行缓冲草稿，切换后同一份文本不会被逐键通道重发。
            self.update_in_document("")
        self._mode = mode
        self._draft = ""
        self._history_index = None
        # 保留当前锚点：行缓冲草稿被移除后，块状光标仍应停在设备光标处。
        if self._enabled:
            self.place_cursor()

    def set_enabled(self, enabled: bool) -> None:
        """切换终端输入模式，并重置历史与草稿锚点。"""
        self._enabled = enabled
        self._history_index = None
        self.reset_anchor()

    def reset_anchor(self) -> None:
        """重置草稿在文档中的锚点位置。"""
        self._input_start_position = 0
        self._cursor_block_number = 0

    def set_submit_handler(self, handler: Callable[[str], bool]) -> None:
        """设置行提交回调；返回 False 时保留输入草稿。"""
        self._submit_handler = handler

    def set_history_provider(self, provider: Callable[[], tuple[str, ...]]) -> None:
        """设置发送历史读取函数。"""
        self._history_provider = provider

    def set_raw_send_handler(self, handler: Callable[[bytes], bool]) -> None:
        """设置原始字节发送回调，用于方向键等按键透传。"""
        self._raw_send = handler

    def set_text_send_handler(self, handler: Callable[[str], bool]) -> None:
        """设置文本发送回调，逐键模式按会话编码发送字符。"""
        self._text_send = handler

    def send_text(self, text: str) -> bool:
        """立即发送一段文本；逐键模式的输入法和粘贴路径复用此入口。"""
        if not text:
            return True
        handler = self._text_send
        return handler(text) if handler is not None else False

    def send_raw_bytes(self, data: bytes) -> bool:
        """立即发送原始终端序列；逐键模式的控制键复用此入口。"""
        if not data:
            return True
        handler = self._raw_send
        return handler(data) if handler is not None else False

    def set_draft(self, text: str) -> None:
        """替换草稿为单行文本（供行缓冲模式的历史菜单回填）。"""
        if self.is_raw:
            return
        self._history_index = None
        self.update_in_document(self._single_line(text))

    def bounds(self) -> tuple[int, int]:
        """返回草稿在文档中的 ``[起点, 终点)`` 位置。"""
        block = self._view.document().findBlockByNumber(self._cursor_block_number)
        text_end = block.position() + len(block.text())
        start = min(self._input_start_position, text_end)
        return start, text_end

    def anchor(self, position: int, block_number: int) -> None:
        """记录渲染方写入草稿后的锚点（由渲染引擎调用）。"""
        self._input_start_position = position
        self._cursor_block_number = block_number

    def place_cursor(self) -> None:
        """把文本光标放到草稿末尾。"""
        _, end = self.bounds()
        caret = QTextCursor(self._view.document())
        caret.setPosition(end)
        self._view.setTextCursor(caret)

    def update_in_document(self, text: str) -> None:
        """把草稿替换为给定文本；逐键模式或画面未就绪时不写文档。"""
        if self.is_raw:
            self._draft = ""
            return
        self._draft = text
        if not self._enabled or not self._is_ready():
            return
        start, end = self.bounds()
        cursor = QTextCursor(self._view.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(text)
        self.place_cursor()
        self._after_edit()

    def sync_from_document(self) -> None:
        """从文档的草稿区间回读当前文本；逐键模式不维护草稿。"""
        if not self._enabled or self.is_raw:
            return
        start, end = self.bounds()
        cursor = QTextCursor(self._view.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self._draft = cursor.selectedText().replace("\u2029", "\n")

    def constrain_cursor(self) -> None:
        """把文本光标限制在草稿区间内；逐键模式由宿主管理选区。"""
        if not self._enabled or self.is_raw:
            return
        start, end = self.bounds()
        cursor = self._view.textCursor()
        if cursor.hasSelection():
            if cursor.selectionStart() < start or cursor.selectionEnd() > end:
                cursor.clearSelection()
                cursor.setPosition(end)
        elif cursor.position() < start or cursor.position() > end:
            cursor.setPosition(min(max(cursor.position(), start), end))
        self._view.setTextCursor(cursor)

    def selection_outside_draft(self) -> bool:
        """返回当前选区是否越出草稿区间。"""
        start, end = self.bounds()
        cursor = self._view.textCursor()
        return cursor.hasSelection() and (
            cursor.selectionStart() < start or cursor.selectionEnd() > end
        )

    def handle_command(self, event: QKeyEvent) -> bool:
        """处理终端命令键；行缓冲模式维护草稿，逐键模式立即发送。"""
        if self.is_raw:
            return self._handle_raw(event)
        handled = False
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self.submit()
            handled = True
        elif event.key() in {Qt.Key.Key_Up, Qt.Key.Key_Down}:
            if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
                self._history_move(older=event.key() == Qt.Key.Key_Up)
            else:
                self._send_arrow_key(up=event.key() == Qt.Key.Key_Up)
            handled = True
        elif event.key() == Qt.Key.Key_Escape:
            self._history_index = None
            self.update_in_document("")
            handled = True
        elif event.matches(QKeySequence.StandardKey.Paste):
            self.constrain_cursor()
            self._view.paste()
            handled = True
        elif event.matches(QKeySequence.StandardKey.Copy):
            self._view.copy()
            handled = True
        elif event.key() == Qt.Key.Key_Home:
            self._move_caret(to_end=False)
            handled = True
        elif event.key() == Qt.Key.Key_End:
            self._move_caret(to_end=True)
            handled = True
        return handled

    def guard_edit(self, event: QKeyEvent) -> bool:
        """拦截会越出草稿区间的剪切、退格与删除按键。"""
        if self.is_raw:
            return True
        start, end = self.bounds()
        cursor = self._view.textCursor()
        blocked = False
        if event.matches(QKeySequence.StandardKey.Cut):
            blocked = self.selection_outside_draft()
        elif event.key() == Qt.Key.Key_Left and not cursor.hasSelection():
            blocked = cursor.position() <= start
        elif event.key() == Qt.Key.Key_Backspace:
            blocked = (
                self.selection_outside_draft()
                if cursor.hasSelection()
                else cursor.position() <= start
            )
        elif event.key() == Qt.Key.Key_Delete:
            blocked = (
                self.selection_outside_draft()
                if cursor.hasSelection()
                else cursor.position() >= end
            )
        return blocked

    def submit(self) -> bool:
        """提交当前草稿；提交成功时清空草稿并重置历史游标。"""
        self.sync_from_document()
        if self._submit_handler is None:
            return False
        if self._submit_handler(self._draft):
            self._history_index = None
            self.update_in_document("")
            return True
        return False

    def submit_line(self, text: str) -> bool:
        """把单行文本放入草稿并立即提交；逐键模式直接提交该行。"""
        self._history_index = None
        if self.is_raw:
            return self._submit_raw_line(self._single_line(text))
        self.update_in_document(self._single_line(text))
        return self.submit()

    def insert_paste(self, text: str) -> None:
        """插入粘贴文本：行缓冲写入草稿，逐键模式立即发送。"""
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        if self.is_raw:
            self._insert_raw_paste(normalized)
            return
        if "\n" not in normalized:
            self._insert_text(normalized)
            return
        for line in normalized.split("\n"):
            if line and not self.submit_line(line):
                return
        self._history_index = None
        self.update_in_document("")

    def handle_raw_input_method(self, commit_text: str) -> bool:
        """逐键模式只发送输入法已提交的文本，忽略预编辑内容。"""
        if not self.is_raw:
            return False
        return self.send_text(commit_text)

    def _handle_raw(self, event: QKeyEvent) -> bool:
        """逐键发送一次按键；未识别的键同样被消费，避免写入终端正文。"""
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self.submit()
            return True
        value = raw_key_input(event.key(), event.text(), event.modifiers())
        if isinstance(value, str):
            self.send_text(value)
        elif isinstance(value, bytes):
            self.send_raw_bytes(value)
        return True

    def _insert_raw_paste(self, normalized: str) -> None:
        """逐键粘贴：单行立即发送，多行按非空行逐行提交。"""
        if "\n" not in normalized:
            self.send_text(normalized)
            return
        for line in normalized.split("\n"):
            if line and not self._submit_raw_line(line):
                return

    def _submit_raw_line(self, text: str) -> bool:
        if self._submit_handler is None:
            return False
        return self._submit_handler(text)

    def _insert_text(self, text: str) -> None:
        self.constrain_cursor()
        cursor = self._view.textCursor()
        cursor.insertText(text)
        self._view.setTextCursor(cursor)
        self.sync_from_document()

    def _move_caret(self, *, to_end: bool) -> None:
        start, end = self.bounds()
        cursor = QTextCursor(self._view.document())
        cursor.setPosition(end if to_end else start)
        self._view.setTextCursor(cursor)

    def _history_move(self, older: bool) -> None:
        history = self._history_provider()
        if not history:
            return
        if self._history_index is None:
            self._history_index = len(history)
        if older:
            self._history_index = max(0, self._history_index - 1)
        else:
            self._history_index = min(len(history), self._history_index + 1)
        value = history[self._history_index] if self._history_index < len(history) else ""
        self.update_in_document(self._single_line(value))

    def _send_arrow_key(self, *, up: bool) -> None:
        """把方向键按 ANSI 序列原样透传给设备。"""
        handler = self._raw_send
        if handler is not None:
            handler(b"\x1b[A" if up else b"\x1b[B")

    @staticmethod
    def _single_line(text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return normalized.split("\n", 1)[0]
