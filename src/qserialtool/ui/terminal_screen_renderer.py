"""终端网格渲染引擎：整屏重建、增量改写与格式写入。"""

from collections.abc import Callable
from datetime import datetime

from PySide6.QtGui import QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

from qserialtool.domain import TerminalCell, TerminalScreen, TerminalStyle
from qserialtool.ui.terminal_inline_input import TerminalInlineInput
from qserialtool.ui.terminal_render_format import (
    format_timestamp,
    highlight_overrides,
    style_format,
    text_format,
)
from qserialtool.ui.terminal_render_plan import (
    MAX_RENDERED_ROWS,
    ScreenWindow,
    can_advance,
    plan_window,
    planned_rewrites,
)
from qserialtool.ui.theme_manager import data_colors


class TerminalScreenRenderer:
    """按 TerminalScreen 快照渲染网格，优先走增量路径。

    ``after_update`` 在每次写入文档后调用（宿主用于自动滚动）；``should_defer``
    返回宿主当前是否处于拖选或存在选中，此时帧更新推迟到交互结束后补画。
    """

    def __init__(
        self,
        view: QPlainTextEdit,
        input_controller: TerminalInlineInput,
        *,
        after_update: Callable[[], None],
        should_defer: Callable[[], bool],
    ) -> None:
        self._view = view
        self._input = input_controller
        self._after_update = after_update
        self._should_defer = should_defer
        self._screen: TerminalScreen | None = None
        self._show_timestamps = False
        self._highlight_enabled = True
        self._deferred = False
        self._rendering = False
        self._rendered_screen: TerminalScreen | None = None
        self._rendered_total = -1
        self._rendered_hidden = 0
        self._rendered_dropped = 0
        self._rendered_cursor: tuple[int, int] | None = None

    @property
    def has_screen(self) -> bool:
        """返回是否已绑定终端画面。"""
        return self._screen is not None

    @property
    def deferred(self) -> bool:
        """返回是否存在等待补画的延迟渲染。"""
        return self._deferred

    def set_show_timestamps(self, enabled: bool) -> None:
        """设置是否在每行前渲染灰色的到达时间前缀。"""
        self._show_timestamps = enabled

    def set_highlight_enabled(self, enabled: bool) -> None:
        """设置是否叠加地址、链接与关键字高亮。"""
        self._highlight_enabled = enabled

    def reset_for_mode(self) -> None:
        """终端模式切换时丢弃画面与延迟渲染状态。"""
        self._screen = None
        self._deferred = False
        self.invalidate()

    def cancel_deferred(self) -> None:
        """丢弃尚未补上的延迟渲染标记。"""
        self._deferred = False

    def invalidate(self) -> None:
        """让下一帧走整屏重建路径。"""
        self._rendered_screen = None
        self._rendered_total = -1
        self._rendered_hidden = 0
        self._rendered_dropped = 0
        self._rendered_cursor = None

    def render(self, screen: TerminalScreen, *, full: bool = False) -> None:
        """更新一帧画面；存在选区或拖选时延迟到交互结束后补画。"""
        self._screen = screen
        if full:
            self.invalidate()
        if self._should_defer():
            self._deferred = True
            return
        self._render_current()

    def flush_deferred(self) -> bool:
        """补上延迟渲染；返回宿主是否可以继续自动滚动。"""
        if self._rendering:
            return False
        if self._deferred:
            self._render_current()
        return True

    def _render_current(self) -> None:
        """重建当前终端画面，供延迟刷新调用。"""
        screen = self._screen
        if screen is None:
            return
        self._deferred = False
        self._rendering = True
        try:
            self._update_screen(screen)
        finally:
            self._rendering = False

    def _update_screen(self, screen: TerminalScreen) -> None:
        """渲染一帧：画面只追加或局部改写时增量更新，否则整屏重建。"""
        if self._can_update_incrementally(screen):
            self._apply_screen_changes(screen)
        else:
            self._rebuild_screen(screen)
        screen.clear_dirty()

    def _can_update_incrementally(self, screen: TerminalScreen) -> bool:
        """判断上一帧状态能否直接演进到当前画面。"""
        if self._rendered_screen is not screen or self._rendered_total < 0:
            return False
        return can_advance(
            screen,
            rendered_total=self._rendered_total,
            rendered_dropped=self._rendered_dropped,
        )

    def _rebuild_screen(self, screen: TerminalScreen) -> None:
        rows = screen.lines()
        hidden = max(len(rows) - MAX_RENDERED_ROWS, 0)
        visible = rows[hidden:]
        cursor_row, cursor_col = screen.cursor
        cursor_row -= hidden
        if cursor_row < 0:
            cursor_row = 0
            cursor_col = 0

        cursor = QTextCursor(self._view.document())
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.removeSelectedText()
        if hidden:
            cursor.setCharFormat(text_format(data_colors().system))
            cursor.insertText(f"… 已隐藏较早的 {hidden} 行\n")
        for index, row in enumerate(visible):
            row_index = hidden + index
            highlights = self._highlight_overrides(row)
            if index == cursor_row:
                self._write_timestamp_prefix(cursor, screen.row_time(row_index))
                self._write_cells(cursor, row, 0, cursor_col, highlights)
                self._input.anchor(cursor.position(), cursor.blockNumber())
                cursor.setCharFormat(style_format(TerminalStyle(), None, self._view.palette()))
                if self._input.draft:
                    cursor.insertText(self._input.draft)
            else:
                self._write_timestamp_prefix(cursor, screen.row_time(row_index))
                self._write_cells(cursor, row, 0, None, highlights)
            if index != len(visible) - 1:
                cursor.insertText("\n")
        cursor.endEditBlock()
        self._rendered_screen = screen
        self._rendered_total = len(rows)
        self._rendered_hidden = hidden
        self._rendered_dropped = screen.dropped_rows
        self._rendered_cursor = (cursor_row, cursor_col)
        self._input.place_cursor()
        self._after_update()

    def _apply_screen_changes(self, screen: TerminalScreen) -> None:
        """只删除顶部滑出窗口的行、追加新行并改写变化行。

        行统一换算成自模型创建起累计的全局行号，屏幕自身裁剪与渲染窗口滑动
        可以同帧发生，文档窗口始终等于全局区间 ``[window_start, window_end)``。
        """
        window = self._screen_window(screen)
        dirty_from, dirty_to = screen.dirty_range()
        rewrites = planned_rewrites(screen, window, self._rendered_cursor)
        if (
            window.drops == 0
            and window.appends == 0
            and not rewrites
            and self._rendered_cursor == (window.visible_cursor, window.cursor_col)
            and not (dirty_from <= window.cursor_row < dirty_to)
        ):
            self._input.place_cursor()
            self._after_update()
            return
        self._write_screen_edits(screen, window, rewrites)
        self._rendered_screen = screen
        self._rendered_total = window.total
        self._rendered_hidden = window.hidden
        self._rendered_dropped = window.dropped
        self._rendered_cursor = (window.visible_cursor, window.cursor_col)
        self._input.place_cursor()
        self._after_update()

    def _screen_window(self, screen: TerminalScreen) -> ScreenWindow:
        """按上一帧状态算出本帧窗口的全局行号几何。"""
        return plan_window(
            screen,
            rendered_total=self._rendered_total,
            rendered_hidden=self._rendered_hidden,
            rendered_dropped=self._rendered_dropped,
        )

    def _write_screen_edits(
        self,
        screen: TerminalScreen,
        window: ScreenWindow,
        rewrites: set[int],
    ) -> None:
        """在一个编辑块内提交结构变更、变化行与新光标行。"""
        header_offset = 1 if window.hidden else 0
        document = self._view.document()
        edit = QTextCursor(document)
        edit.beginEditBlock()
        try:
            if window.drops > 0:
                self._drop_top_lines(
                    header_offset=1 if self._rendered_hidden else 0,
                    count=window.drops,
                )
            if window.hidden > 0:
                header_text = f"… 已隐藏较早的 {window.hidden} 行"
                if self._rendered_hidden == 0:
                    header = QTextCursor(document)
                    header.movePosition(QTextCursor.MoveOperation.Start)
                    header.setCharFormat(text_format(data_colors().system))
                    header.insertText(header_text + "\n")
                elif window.hidden != self._rendered_hidden:
                    self._replace_block_text(0, header_text, text_format(data_colors().system))
            for row_index in sorted(rewrites):
                self._replace_block_line(
                    row_index - window.hidden + header_offset,
                    screen.row(row_index),
                    screen.row_time(row_index),
                )
            if window.appends > 0:
                self._append_rows(screen, window.append_start_row, window.total)
            self._replace_cursor_block(
                window.visible_cursor + header_offset,
                screen.row(window.cursor_row),
                window.cursor_col,
                screen.row_time(window.cursor_row),
            )
        finally:
            edit.endEditBlock()

    def _drop_top_lines(self, *, header_offset: int, count: int) -> None:
        """删除文档顶部 count 个内容块，保留表头行。"""
        document = self._view.document()
        first = document.findBlockByNumber(header_offset)
        last = document.findBlockByNumber(header_offset + count)
        cutter = QTextCursor(document)
        cutter.setPosition(first.position())
        cutter.setPosition(last.position(), QTextCursor.MoveMode.KeepAnchor)
        cutter.removeSelectedText()

    def _replace_block_text(
        self, block_number: int, text: str, char_format: QTextCharFormat
    ) -> None:
        cursor = self._cleared_line_cursor(block_number)
        cursor.setCharFormat(char_format)
        cursor.insertText(text)

    def _replace_block_line(
        self,
        block_number: int,
        row: tuple[TerminalCell, ...],
        time: datetime | None,
    ) -> None:
        cursor = self._cleared_line_cursor(block_number)
        self._write_timestamp_prefix(cursor, time)
        self._write_cells(cursor, row, 0, None, self._highlight_overrides(row))

    def _replace_cursor_block(
        self,
        block_number: int,
        row: tuple[TerminalCell, ...],
        cursor_col: int,
        time: datetime | None,
    ) -> None:
        """重写光标行：只在光标前渲染单元格，草稿接在其后。"""
        cursor = self._cleared_line_cursor(block_number)
        self._write_timestamp_prefix(cursor, time)
        self._write_cells(cursor, row, 0, cursor_col, self._highlight_overrides(row))
        self._input.anchor(cursor.position(), cursor.blockNumber())
        cursor.setCharFormat(style_format(TerminalStyle(), None, self._view.palette()))
        if self._input.draft:
            cursor.insertText(self._input.draft)

    def _cleared_line_cursor(self, block_number: int) -> QTextCursor:
        """返回位于目标行、且已清掉原行文本的光标。"""
        block = self._view.document().findBlockByNumber(block_number)
        cursor = QTextCursor(self._view.document())
        cursor.setPosition(block.position())
        cursor.setPosition(
            block.position() + len(block.text()),
            QTextCursor.MoveMode.KeepAnchor,
        )
        cursor.removeSelectedText()
        return cursor

    def _append_rows(self, screen: TerminalScreen, start: int, end: int) -> None:
        """在文档末尾追加 [start, end) 行。"""
        cursor = QTextCursor(self._view.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for row_index in range(start, end):
            row = screen.row(row_index)
            cursor.insertText("\n")
            self._write_timestamp_prefix(cursor, screen.row_time(row_index))
            self._write_cells(cursor, row, 0, None, self._highlight_overrides(row))

    def _write_timestamp_prefix(self, cursor: QTextCursor, time: datetime | None) -> None:
        """按需在行首写入灰色时间前缀；复制选中内容时会包含该前缀。"""
        if not self._show_timestamps or time is None:
            return
        cursor.setCharFormat(text_format(data_colors().system))
        cursor.insertText(format_timestamp(time))

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
            cursor.setCharFormat(style_format(style, override, self._view.palette()))
            cursor.insertText(text)
        if end is not None and end > len(row):
            cursor.setCharFormat(style_format(TerminalStyle(), None, self._view.palette()))
            cursor.insertText(" " * (end - len(row)))

    def _highlight_overrides(self, row: tuple[TerminalCell, ...]) -> dict[int, str]:
        """按行文本匹配地址与链接，返回需要改色的单元格索引到颜色。"""
        if not self._highlight_enabled:
            return {}
        return highlight_overrides(row)
