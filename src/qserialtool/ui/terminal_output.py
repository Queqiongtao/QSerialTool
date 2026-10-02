"""日志区内联输入控件。"""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeyEvent, QKeySequence, QPalette, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QWidget


class TerminalOutput(QPlainTextEdit):
    """显示原始接收流，并把单行输入维护为流末尾的可删除草稿。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._terminal_mode = False
        self._draft = ""
        self._input_start_position = 0
        self._history_provider: Callable[[], tuple[str, ...]] = lambda: ()
        self._submit_handler: Callable[[str], bool] | None = None
        self._history_index: int | None = None
        self._autoscroll = True
        self._batch_update = False
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setAcceptDrops(False)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    @property
    def draft(self) -> str:
        """返回当前终端输入草稿。"""
        return self._draft

    def set_terminal_mode(self, enabled: bool) -> None:
        """启用或关闭原始流末尾的内联输入。"""
        if self._terminal_mode == enabled:
            return
        if self._terminal_mode:
            self._remove_draft()
        self._terminal_mode = enabled
        self._history_index = None
        super().clear()
        self._input_start_position = 0
        if enabled:
            self.setReadOnly(False)
            self._append_draft()
        else:
            self.setReadOnly(True)

    def set_submit_handler(self, handler: Callable[[str], bool]) -> None:
        """设置行提交回调；返回 False 时保留输入草稿。"""
        self._submit_handler = handler

    def set_history_provider(self, provider: Callable[[], tuple[str, ...]]) -> None:
        """设置发送历史读取函数。"""
        self._history_provider = provider

    def set_autoscroll(self, enabled: bool) -> None:
        """设置新记录到达时是否自动滚动。"""
        self._autoscroll = enabled

    def set_draft(self, text: str) -> None:
        """替换终端草稿，供历史菜单回填。"""
        self._draft = self._single_line(text)
        self._history_index = None
        self._replace_draft()
        self.focus_input()

    def focus_input(self) -> None:
        """把焦点和光标移到流末尾的输入区。"""
        if not self._terminal_mode:
            return
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def begin_batch_update(self) -> None:
        """批量追加日志时暂时移除输入草稿，避免重复重建。"""
        self._remove_draft()
        self._batch_update = True

    def end_batch_update(self) -> None:
        """结束批量追加并恢复输入草稿。"""
        self._batch_update = False
        self._append_draft()
        self._scroll_after_update()

    def clear_content(self) -> None:
        """清空终端画面但保留当前输入草稿。"""
        self._remove_draft()
        super().clear()
        self._input_start_position = 0
        self._append_draft()
        self._scroll_after_update()

    def append_text(self, text: str, color: str) -> None:
        """按日志格式追加一行文本。"""
        self._remove_draft()
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.setCharFormat(self._format_for(color))
        cursor.insertText(text + "\n")
        if self._terminal_mode and not self._batch_update:
            self._append_draft()
            self._scroll_after_update()

    def append_stream(self, text: str, color: str) -> None:
        """把原始接收文本直接追加到终端流末尾。"""
        if not self._terminal_mode or not text:
            return
        self._remove_draft()
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.setCharFormat(self._format_for(color))
        cursor.insertText(text)
        self._input_start_position = cursor.position()
        self._append_draft()
        self._scroll_after_update()

    def replace_stream(self, chunks: tuple[tuple[str, str], ...]) -> None:
        """用原始接收块重建终端流，并保留当前草稿。"""
        if not self._terminal_mode:
            return
        self._remove_draft()
        super().clear()
        self._input_start_position = 0
        cursor = QTextCursor(self.document())
        for text, color in chunks:
            if not text:
                continue
            cursor.setCharFormat(self._format_for(color))
            cursor.insertText(text)
        self._input_start_position = cursor.position()
        self._append_draft()
        self._scroll_after_update()

    def _format_for(self, color: str) -> QTextCharFormat:
        text_format = QTextCharFormat()
        text_format.setForeground(QColor(color))
        return text_format

    def _append_draft(self) -> None:
        if not self._terminal_mode:
            return
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._input_start_position = cursor.position()
        if self._draft:
            draft_format = QTextCharFormat()
            draft_format.setForeground(self.palette().color(QPalette.ColorRole.Text))
            cursor.setCharFormat(draft_format)
            cursor.insertText(self._draft)
        self.setTextCursor(cursor)

    def _remove_draft(self) -> None:
        if not self._terminal_mode:
            return
        document_end = self.document().characterCount() - 1
        start = min(self._input_start_position, document_end)
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        self._input_start_position = start
        self.setTextCursor(cursor)

    def _replace_draft(self) -> None:
        if not self._terminal_mode:
            return
        self._remove_draft()
        self._append_draft()
        self._scroll_after_update()

    def _scroll_after_update(self) -> None:
        if self._autoscroll:
            self.moveCursor(QTextCursor.MoveOperation.End)
            self.ensureCursorVisible()

    def _input_start(self) -> int:
        return self._input_start_position

    def _sync_draft_from_document(self) -> None:
        if not self._terminal_mode:
            return
        document_end = self.document().characterCount() - 1
        start = min(self._input_start_position, document_end)
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        self._draft = cursor.selectedText().replace("\u2029", "\n")

    def _constrain_cursor(self) -> None:
        if not self._terminal_mode:
            return
        start = self._input_start()
        cursor = self.textCursor()
        if cursor.hasSelection() and cursor.selectionStart() < start:
            cursor.clearSelection()
            cursor.movePosition(QTextCursor.MoveOperation.End)
        elif not cursor.hasSelection() and cursor.position() < start:
            cursor.setPosition(start)
        self.setTextCursor(cursor)

    def _selection_touches_history(self) -> bool:
        cursor = self.textCursor()
        return cursor.hasSelection() and cursor.selectionStart() < self._input_start()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """限制编辑范围，并把回车和上下键交给终端命令处理。"""
        if not self._terminal_mode:
            super().keyPressEvent(event)
            return
        if self._handle_terminal_command(event) or self._guard_edit_key(event):
            return
        self._constrain_cursor()
        super().keyPressEvent(event)
        self._sync_draft_from_document()

    def _handle_terminal_command(self, event: QKeyEvent) -> bool:
        handled = False
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            self._submit_current()
            handled = True
        elif event.key() in {Qt.Key.Key_Up, Qt.Key.Key_Down}:
            self._history_move(older=event.key() == Qt.Key.Key_Up)
            handled = True
        elif event.key() == Qt.Key.Key_Escape:
            self._draft = ""
            self._history_index = None
            self._replace_draft()
            handled = True
        elif event.matches(QKeySequence.StandardKey.Paste):
            self.paste()
            handled = True
        elif event.key() == Qt.Key.Key_Home:
            cursor = self.textCursor()
            cursor.setPosition(self._input_start())
            self.setTextCursor(cursor)
            handled = True
        elif event.key() == Qt.Key.Key_End:
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.setTextCursor(cursor)
            handled = True
        return handled

    def _guard_edit_key(self, event: QKeyEvent) -> bool:
        cursor = self.textCursor()
        blocked = False
        if event.matches(QKeySequence.StandardKey.Cut) and self._selection_touches_history():
            blocked = True
        elif event.key() == Qt.Key.Key_Left and not cursor.hasSelection():
            blocked = cursor.position() <= self._input_start()
        elif event.key() == Qt.Key.Key_Backspace:
            if cursor.position() <= self._input_start() and not cursor.hasSelection():
                blocked = True
            else:
                blocked = self._selection_touches_history()
        elif event.key() == Qt.Key.Key_Delete:
            if cursor.position() >= self.document().characterCount() - 1:
                blocked = True
            else:
                blocked = self._selection_touches_history()
        return blocked

    def _submit_current(self) -> bool:
        self._sync_draft_from_document()
        if self._submit_handler is None:
            return False
        if self._submit_handler(self._draft):
            self._draft = ""
            self._history_index = None
            self._remove_draft()
            return True
        self._replace_draft()
        return False

    def _submit_text(self, text: str) -> bool:
        self._draft = self._single_line(text)
        self._history_index = None
        self._replace_draft()
        return self._submit_current()

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
        self._draft = self._single_line(value)
        self._replace_draft()

    @staticmethod
    def _single_line(text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return normalized.split("\n", 1)[0]

    def insertFromMimeData(self, source: object) -> None:
        """粘贴单行文本；多行文本按非空行依次发送。"""
        if not self._terminal_mode:
            super().insertFromMimeData(source)
            return
        text = source.text().replace("\r\n", "\n").replace("\r", "\n")
        if "\n" not in text:
            self._insert_text(text)
            return
        for line in text.split("\n"):
            if line and not self._submit_text(line):
                return
        self._draft = ""
        self._history_index = None
        self._remove_draft()

    def inputMethodEvent(self, event: object) -> None:
        """让输入法文本继续受终端输入区约束。"""
        if not self._terminal_mode:
            super().inputMethodEvent(event)
            return
        self._constrain_cursor()
        super().inputMethodEvent(event)
        self._sync_draft_from_document()

    def _insert_text(self, text: str) -> None:
        self._constrain_cursor()
        cursor = self.textCursor()
        cursor.insertText(text)
        self.setTextCursor(cursor)
        self._sync_draft_from_document()
