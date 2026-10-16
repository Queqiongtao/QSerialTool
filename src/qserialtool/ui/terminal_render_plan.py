"""终端渲染窗口的几何规划：增量可行性判断与全局行号换算。"""

from dataclasses import dataclass

from qserialtool.domain import TerminalScreen

# 画面只渲染最近若干行，更早的滚动历史由终端模型保留。
MAX_RENDERED_ROWS = 2000


@dataclass(frozen=True, slots=True)
class ScreenWindow:
    """一帧增量更新的几何：模型行号与文档窗口都换算成全局行号。"""

    total: int
    hidden: int
    dropped: int
    cursor_row: int
    cursor_col: int
    visible_cursor: int
    window_start: int
    previous_start: int
    previous_end: int
    drops: int
    appends: int
    append_start_row: int


def can_advance(
    screen: TerminalScreen,
    *,
    rendered_total: int,
    rendered_dropped: int,
) -> bool:
    """判断上一帧状态能否直接演进到当前画面（屏幕对象同一性由调用方判断）。"""
    total = screen.row_count
    if total < rendered_total or screen.dropped_rows < rendered_dropped:
        return False
    hidden = max(total - MAX_RENDERED_ROWS, 0)
    window_start = screen.dropped_rows + hidden
    previous_end = rendered_dropped + rendered_total
    if window_start >= previous_end:
        # 上一帧窗口整体滑出，整屏重建更简单。
        return False
    cursor_row, _ = screen.cursor
    # 光标已在渲染窗口之上时交由整屏重建处理其钳制语义。
    return cursor_row >= hidden


def plan_window(
    screen: TerminalScreen,
    *,
    rendered_total: int,
    rendered_hidden: int,
    rendered_dropped: int,
) -> ScreenWindow:
    """按上一帧状态算出本帧窗口的全局行号几何。"""
    total = screen.row_count
    hidden = max(total - MAX_RENDERED_ROWS, 0)
    dropped = screen.dropped_rows
    cursor_row, cursor_col = screen.cursor
    previous_start = rendered_dropped + rendered_hidden
    previous_end = rendered_dropped + rendered_total
    return ScreenWindow(
        total=total,
        hidden=hidden,
        dropped=dropped,
        cursor_row=cursor_row,
        cursor_col=cursor_col,
        visible_cursor=cursor_row - hidden,
        window_start=dropped + hidden,
        previous_start=previous_start,
        previous_end=previous_end,
        drops=dropped + hidden - previous_start,
        appends=dropped + total - previous_end,
        append_start_row=previous_end - dropped,
    )


def planned_rewrites(
    screen: TerminalScreen,
    window: ScreenWindow,
    rendered_cursor: tuple[int, int] | None,
) -> set[int]:
    """返回需要原位改写的屏幕行，含窗口滑动后要还原的旧草稿行。"""
    dirty_from, dirty_to = screen.dirty_range()
    rewrites = set(range(max(dirty_from, window.hidden), min(dirty_to, window.append_start_row)))
    if rendered_cursor is not None:
        # 旧草稿行换算到本帧的文档行号；还在窗口内且不再是光标行时要还原成普通行。
        previous_line = window.previous_start + rendered_cursor[0] - window.window_start
        if previous_line >= 0 and previous_line != window.visible_cursor:
            rewrites.add(previous_line + window.hidden)
    return rewrites
