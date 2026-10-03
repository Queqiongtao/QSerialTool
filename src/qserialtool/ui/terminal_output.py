"""终端视图控件：渲染终端网格并提供光标处的内联输入。"""

from collections.abc import Callable

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QFont,
    QKeyEvent,
    QKeySequence,
    QPainter,
    QPaintEvent,
    QPalette,
    QTextCharFormat,
    QTextCursor,
    QTextOption,
)
from PySide6.QtWidgets import QMenu, QPlainTextEdit, QWidget

from qserialtool.domain import TerminalCell, TerminalScreen, TerminalStyle
from qserialtool.ui.terminal_highlight import find_highlights
from qserialtool.ui.theme_manager import ansi_color, data_colors, highlight_colors

# 画面只渲染最近若干行，更早的滚动历史由终端模型保留。
_MAX_RENDERED_ROWS = 2000


class TerminalOutput(QPlainTextEdit):
    """渲染终端网格，并把单行输入维护为光标处的可编辑草稿。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._terminal_mode = False
        self._screen: TerminalScreen | None = None
        self._draft = ""
        self._input_start_position = 0
        self._cursor_block_number = 0
        self._history_provider: Callable[[], tuple[str, ...]] = lambda: ()
        self._submit_handler: Callable[[str], bool] | None = None
        self._history_index: int | None = None
        self._autoscroll = True
        self._batch_update = False
        self._highlight_enabled = True
        self._deferred_render = False
        self._rendering = False
        self._scrolling = False
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setAcceptDrops(False)
        self.setCursorWidth(0)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.selectionChanged.connect(self._on_selection_changed)

    @property
    def draft(self) -> str:
        """返回当前终端输入草稿。"""
        return self._draft

    def set_terminal_mode(self, enabled: bool) -> None:
        """启用或关闭终端网格渲染与内联输入。"""
        if self._terminal_mode == enabled:
            return
        self._terminal_mode = enabled
        self._screen = None
        self._history_index = None
        self._input_start_position = 0
        self._cursor_block_number = 0
        self._deferred_render = False
        super().clear()
        self.setReadOnly(not enabled)

    def set_submit_handler(self, handler: Callable[[str], bool]) -> None:
        """设置行提交回调；返回 False 时保留输入草稿。"""
        self._submit_handler = handler

    def set_history_provider(self, provider: Callable[[], tuple[str, ...]]) -> None:
        """设置发送历史读取函数。"""
        self._history_provider = provider

    def set_autoscroll(self, enabled: bool) -> None:
        """设置新记录到达时是否自动滚动。"""
        self._autoscroll = enabled

    def set_highlight_enabled(self, enabled: bool) -> None:
        """设置是否在终端视图中叠加地址、链接与关键字高亮。"""
        self._highlight_enabled = enabled

    def set_wrap_enabled(self, enabled: bool) -> None:
        """设置超长行是否按控件宽度自动换行。"""
        if enabled:
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            self.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        else:
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def set_draft(self, text: str) -> None:
        """替换终端草稿，供历史菜单回填。"""
        self._history_index = None
        self._update_draft(self._single_line(text))
        self.focus_input()

    def focus_input(self) -> None:
        """把焦点和光标移到输入草稿末尾。"""
        if not self._terminal_mode:
            return
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        if self._screen is not None:
            self._place_input_cursor()
            self.ensureCursorVisible()

    def begin_batch_update(self) -> None:
        """分栏视图批量追加期间暂停滚动。"""
        self._batch_update = True

    def end_batch_update(self) -> None:
        """结束批量追加并滚动到末尾。"""
        self._batch_update = False
        self._scroll_after_update()

    def clear_content(self) -> None:
        """清空控件内容；终端模式由调用方随后重建画面。"""
        self._deferred_render = False
        super().clear()
        self._input_start_position = 0
        self._cursor_block_number = 0

    def append_text(self, text: str, color: str) -> None:
        """按日志格式追加一行文本，供分栏视图使用。"""
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.setCharFormat(self._format_for(color))
        cursor.insertText(text + "\n")
        if not self._batch_update:
            self._scroll_after_update()

    def render_screen(self, screen: TerminalScreen) -> None:
        """按终端模型重建画面，并在光标处渲染输入草稿。"""
        if not self._terminal_mode:
            return
        self._screen = screen
        if self.textCursor().hasSelection():
            self._deferred_render = True
            return
        self._render_current_screen()

    def _render_current_screen(self) -> None:
        """重建当前终端画面，供延迟刷新调用。"""
        screen = self._screen
        if screen is None:
            return
        self._deferred_render = False
        self._rendering = True
        try:
            self._rebuild_screen(screen)
        finally:
            self._rendering = False

    def _rebuild_screen(self, screen: TerminalScreen) -> None:
        rows = screen.lines()
        hidden = max(len(rows) - _MAX_RENDERED_ROWS, 0)
        visible = rows[hidden:]
        cursor_row, cursor_col = screen.cursor
        cursor_row -= hidden
        if cursor_row < 0:
            cursor_row = 0
            cursor_col = 0

        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.removeSelectedText()
        if hidden:
            cursor.setCharFormat(self._format_for(data_colors().system))
            cursor.insertText(f"… 已隐藏较早的 {hidden} 行\n")
        for index, row in enumerate(visible):
            highlights = self._highlight_overrides(row)
            if index == cursor_row:
                self._write_cells(cursor, row, 0, cursor_col, highlights)
                self._input_start_position = cursor.position()
                cursor.setCharFormat(self._format_for_style(TerminalStyle()))
                if self._draft:
                    cursor.insertText(self._draft)
                self._cursor_block_number = cursor.blockNumber()
            else:
                self._write_cells(cursor, row, 0, None, highlights)
            if index != len(visible) - 1:
                cursor.insertText("\n")
        cursor.endEditBlock()
        self._place_input_cursor()
        self._scroll_after_update()

    def _write_cells(
        self,
        cursor: QTextCursor,
        row: tuple[TerminalCell, ...],
        start: int,
        end: int | None,
        highlights: dict[int, str],
    ) -> None:
        limit = len(row) if end is None else min(end, len(row))
        index = start
        while index < limit:
            cell = row[index]
            if cell.trailing:
                index += 1
                continue
            style = cell.style
            override = highlights.get(index)
            text = cell.char
            index += 1
            while (
                index < limit
                and not row[index].trailing
                and row[index].style == style
                and highlights.get(index) == override
            ):
                text += row[index].char
                index += 1
            cursor.setCharFormat(self._format_for_style(style, override))
            cursor.insertText(text)
        if end is not None and end > len(row):
            cursor.setCharFormat(self._format_for_style(TerminalStyle()))
            cursor.insertText(" " * (end - len(row)))

    def _format_for(self, color: str) -> QTextCharFormat:
        text_format = QTextCharFormat()
        text_format.setForeground(QColor(color))
        return text_format

    def _highlight_overrides(self, row: tuple[TerminalCell, ...]) -> dict[int, str]:
        """按行文本匹配地址与链接，返回需要改色的单元格索引到颜色。"""
        if not self._highlight_enabled:
            return {}
        matches = find_highlights("".join(cell.char for cell in row))
        if not matches:
            return {}
        colors = highlight_colors()
        palette = {
            "address": colors.address,
            "link": colors.link,
            "success": colors.success,
            "error": colors.error,
            "warning": colors.warning,
        }
        positions: list[tuple[int, int, int]] = []
        offset = 0
        for cell_index, cell in enumerate(row):
            length = len(cell.char)
            positions.append((offset, offset + length, cell_index))
            offset += length
        overrides: dict[int, str] = {}
        for start, end, kind in matches:
            for cell_start, cell_end, cell_index in positions:
                if cell_start >= end:
                    break
                cell = row[cell_index]
                if cell.trailing or cell.style.fg is not None:
                    continue
                if cell_end > start:
                    overrides[cell_index] = palette[kind]
        return overrides

    def _format_for_style(
        self,
        style: TerminalStyle,
        override: str | None = None,
    ) -> QTextCharFormat:
        text_format = QTextCharFormat()
        palette = self.palette()
        if override is not None:
            text_format.setForeground(QColor(override))
        elif style.fg is None:
            text_format.setForeground(palette.color(QPalette.ColorRole.Text))
        else:
            text_format.setForeground(QColor(ansi_color(style.fg)))
        if style.bg is not None:
            text_format.setBackground(QColor(ansi_color(style.bg)))
        if style.bold:
            text_format.setFontWeight(QFont.Weight.Bold)
        return text_format

    def _draft_bounds(self) -> tuple[int, int]:
        block = self.document().findBlockByNumber(self._cursor_block_number)
        text_end = block.position() + len(block.text())
        start = min(self._input_start_position, text_end)
        return start, text_end

    def paintEvent(self, event: QPaintEvent) -> None:
        """在草稿末尾绘制块状光标，避免污染正文内容。"""
        super().paintEvent(event)
        if not self._terminal_mode or self._screen is None:
            return
        caret = QTextCursor(self.document())
        caret.setPosition(self._draft_bounds()[1])
        rect = self.cursorRect(caret)
        width = max(self.fontMetrics().horizontalAdvance(" "), 1)
        painter = QPainter(self.viewport())
        painter.fillRect(
            QRect(rect.left(), rect.top(), width, rect.height()),
            self.palette().color(QPalette.ColorRole.Text),
        )

    def _place_input_cursor(self) -> None:
        _, end = self._draft_bounds()
        caret = QTextCursor(self.document())
        caret.setPosition(end)
        self.setTextCursor(caret)

    def _scroll_after_update(self) -> None:
        """自动滚动到末尾；存在选中内容或正在滚动时保持原位。"""
        if not self._autoscroll or self._scrolling:
            return
        if self.textCursor().hasSelection():
            return
        self._scrolling = True
        try:
            self.moveCursor(QTextCursor.MoveOperation.End)
            self.ensureCursorVisible()
        finally:
            self._scrolling = False

    def _on_selection_changed(self) -> None:
        """选中被清除后补上暂停期间延迟的渲染与自动滚动。"""
        if self._rendering or self._scrolling or self.textCursor().hasSelection():
            return
        if self._deferred_render:
            self._render_current_screen()
        self._scroll_after_update()

    def _update_draft(self, text: str) -> None:
        self._draft = text
        if not self._terminal_mode or self._screen is None:
            return
        start, end = self._draft_bounds()
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(text)
        self._place_input_cursor()
        self._scroll_after_update()

    def _sync_draft_from_document(self) -> None:
        if not self._terminal_mode:
            return
        start, end = self._draft_bounds()
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self._draft = cursor.selectedText().replace("\u2029", "\n")

    def _constrain_cursor(self) -> None:
        if not self._terminal_mode:
            return
        start, end = self._draft_bounds()
        cursor = self.textCursor()
        if cursor.hasSelection():
            if cursor.selectionStart() < start or cursor.selectionEnd() > end:
                cursor.clearSelection()
                cursor.setPosition(end)
        elif cursor.position() < start or cursor.position() > end:
            cursor.setPosition(min(max(cursor.position(), start), end))
        self.setTextCursor(cursor)

    def _selection_outside_draft(self) -> bool:
        start, end = self._draft_bounds()
        cursor = self.textCursor()
        return cursor.hasSelection() and (
            cursor.selectionStart() < start or cursor.selectionEnd() > end
        )

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """接收区右键只提供复制与全选，避免剪切/删除改到日志内容。"""
        self._build_context_menu().exec(event.globalPos())

    def _build_context_menu(self) -> QMenu:
        """构造受限的右键菜单：只有复制和全选。"""
        menu = QMenu(self)
        copy_action = menu.addAction("复制")
        copy_action.setEnabled(self.textCursor().hasSelection())
        copy_action.triggered.connect(self.copy)
        select_all_action = menu.addAction("全选")
        select_all_action.triggered.connect(self.selectAll)
        return menu

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
            self._history_index = None
            self._update_draft("")
            handled = True
        elif event.matches(QKeySequence.StandardKey.Paste):
            self._constrain_cursor()
            self.paste()
            handled = True
        elif event.matches(QKeySequence.StandardKey.Copy):
            self.copy()
            handled = True
        elif event.key() == Qt.Key.Key_Home:
            self._move_input_caret(to_end=False)
            handled = True
        elif event.key() == Qt.Key.Key_End:
            self._move_input_caret(to_end=True)
            handled = True
        return handled

    def _move_input_caret(self, *, to_end: bool) -> None:
        start, end = self._draft_bounds()
        cursor = QTextCursor(self.document())
        cursor.setPosition(end if to_end else start)
        self.setTextCursor(cursor)

    def _guard_edit_key(self, event: QKeyEvent) -> bool:
        start, end = self._draft_bounds()
        cursor = self.textCursor()
        blocked = False
        if event.matches(QKeySequence.StandardKey.Cut):
            blocked = self._selection_outside_draft()
        elif event.key() == Qt.Key.Key_Left and not cursor.hasSelection():
            blocked = cursor.position() <= start
        elif event.key() == Qt.Key.Key_Backspace:
            blocked = (
                self._selection_outside_draft()
                if cursor.hasSelection()
                else cursor.position() <= start
            )
        elif event.key() == Qt.Key.Key_Delete:
            blocked = (
                self._selection_outside_draft()
                if cursor.hasSelection()
                else cursor.position() >= end
            )
        return blocked

    def _submit_current(self) -> bool:
        self._sync_draft_from_document()
        if self._submit_handler is None:
            return False
        if self._submit_handler(self._draft):
            self._history_index = None
            self._update_draft("")
            return True
        return False

    def _submit_text(self, text: str) -> bool:
        self._history_index = None
        self._update_draft(self._single_line(text))
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
        self._update_draft(self._single_line(value))

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
        self._history_index = None
        self._update_draft("")

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
