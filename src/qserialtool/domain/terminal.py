"""行式滚动缓冲终端模型，解析常见 ANSI 转义序列。"""

from dataclasses import dataclass, replace
from datetime import datetime
from unicodedata import combining, east_asian_width

from .errors import ValidationError

DEFAULT_MAX_ROWS = 5000
DEFAULT_MAX_COLUMNS = 500
TAB_WIDTH = 8

_WIDE_CATEGORIES = frozenset({"W", "F"})
_PRIVATE_MARKERS = frozenset({"?", ">", "=", "!"})

# SGR 参数区间
_SGR_BOLD_RESET = 22
_SGR_FG_MIN, _SGR_FG_MAX = 30, 37
_SGR_FG_DEFAULT = 39
_SGR_BG_MIN, _SGR_BG_MAX = 40, 47
_SGR_BG_DEFAULT = 49
_SGR_BRIGHT_FG_MIN, _SGR_BRIGHT_FG_MAX = 90, 97
_SGR_BRIGHT_BG_MIN, _SGR_BRIGHT_BG_MAX = 100, 107
_BRIGHT_OFFSET = 8
_SGR_EXTENDED_FG = 38
_SGR_EXTENDED_BG = 48
_SGR_PALETTE = 5
_SGR_TRUECOLOR = 2
_MAX_PALETTE_INDEX = 255

# CSI 参数字节与中间字节区间
_CSI_PARAMETER_MIN, _CSI_PARAMETER_MAX = 0x30, 0x3F
_CSI_INTERMEDIATE_MIN, _CSI_INTERMEDIATE_MAX = 0x20, 0x2F

_ERASE_TO_END = 0
_ERASE_TO_START = 1
_ERASE_ALL = 2
_WIDE_WIDTH = 2


@dataclass(frozen=True, slots=True)
class TerminalStyle:
    """单元格的语义样式，渲染时再映射到当前主题颜色。"""

    fg: int | None = None
    bg: int | None = None
    bold: bool = False

    def apply_sgr(self, params: list[int]) -> "TerminalStyle":
        """按 SGR 参数返回新样式，无法识别的参数组整体跳过。"""
        style = self
        index = 0
        total = len(params)
        while index < total:
            value = params[index]
            if value == 0:
                style = TerminalStyle()
            elif value == 1:
                style = replace(style, bold=True)
            elif value == _SGR_BOLD_RESET:
                style = replace(style, bold=False)
            elif _SGR_FG_MIN <= value <= _SGR_FG_MAX:
                style = replace(style, fg=value - _SGR_FG_MIN)
            elif value == _SGR_FG_DEFAULT:
                style = replace(style, fg=None)
            elif _SGR_BG_MIN <= value <= _SGR_BG_MAX:
                style = replace(style, bg=value - _SGR_BG_MIN)
            elif value == _SGR_BG_DEFAULT:
                style = replace(style, bg=None)
            elif _SGR_BRIGHT_FG_MIN <= value <= _SGR_BRIGHT_FG_MAX:
                style = replace(style, fg=value - _SGR_BRIGHT_FG_MIN + _BRIGHT_OFFSET)
            elif _SGR_BRIGHT_BG_MIN <= value <= _SGR_BRIGHT_BG_MAX:
                style = replace(style, bg=value - _SGR_BRIGHT_BG_MIN + _BRIGHT_OFFSET)
            elif value in {_SGR_EXTENDED_FG, _SGR_EXTENDED_BG}:
                style, consumed = TerminalStyle._apply_extended_color(
                    style,
                    params,
                    index,
                    background=value == _SGR_EXTENDED_BG,
                )
                if consumed == 0:
                    break
                index += consumed
                continue
            index += 1
        return style

    @staticmethod
    def _apply_extended_color(
        style: "TerminalStyle",
        params: list[int],
        index: int,
        *,
        background: bool,
    ) -> tuple["TerminalStyle", int]:
        """解析 38/48 扩展颜色；返回新样式与消耗的参数个数，0 表示参数不完整。"""
        if index + 1 >= len(params):
            return style, 0
        selector = params[index + 1]
        if selector == _SGR_PALETTE:
            if index + 2 >= len(params):
                return style, 0
            value = params[index + 2]
            if 0 <= value <= _MAX_PALETTE_INDEX:
                style = replace(style, bg=value) if background else replace(style, fg=value)
            return style, 3
        if selector == _SGR_TRUECOLOR:
            if index + 4 >= len(params):
                return style, 0
            return style, 5
        return style, 1


DEFAULT_STYLE = TerminalStyle()


@dataclass(frozen=True, slots=True)
class TerminalCell:
    """一个终端单元格；trailing 表示双宽字符的右半格。"""

    char: str = " "
    style: TerminalStyle = DEFAULT_STYLE
    trailing: bool = False


class TerminalScreen:
    """维护行式滚动缓冲、光标位置、当前样式与行时间元数据。"""

    def __init__(
        self,
        *,
        max_rows: int = DEFAULT_MAX_ROWS,
        max_columns: int = DEFAULT_MAX_COLUMNS,
    ) -> None:
        if type(max_rows) is not int or max_rows <= 0:
            raise ValidationError("终端最大行数必须是正整数。")
        if type(max_columns) is not int or max_columns <= 0:
            raise ValidationError("终端最大列数必须是正整数。")
        self._max_rows = max_rows
        self._max_columns = max_columns
        self._rows: list[list[TerminalCell]] = [[]]
        self._row_times: list[datetime | None] = [None]
        self._cursor_row = 0
        self._cursor_col = 0
        self._style = DEFAULT_STYLE
        self._pending = ""
        self._active_time: datetime | None = None
        self._dropped = 0
        self._dirty_from: int | None = None
        self._dirty_to = 0

    @property
    def cursor(self) -> tuple[int, int]:
        """返回光标所在的行与列。"""
        return self._cursor_row, self._cursor_col

    @property
    def max_columns(self) -> int:
        """返回单行最大列数。"""
        return self._max_columns

    @property
    def row_count(self) -> int:
        """返回当前行数，渲染方可据此增量取行而不整屏复制。"""
        return len(self._rows)

    @property
    def dropped_rows(self) -> int:
        """返回已从顶部淘汰的行数，供渲染方对齐滚动窗口的内容位置。"""
        return self._dropped

    def row(self, index: int) -> tuple[TerminalCell, ...]:
        """返回单行只读快照。"""
        return tuple(self._rows[index])

    def row_time(self, index: int) -> datetime | None:
        """返回该行首次被写入时的时间；未写入、已淘汰或已整屏重置时为 ``None``。"""
        return self._row_times[index]

    def lines(self) -> tuple[tuple[TerminalCell, ...], ...]:
        """返回只读的行快照。"""
        return tuple(tuple(row) for row in self._rows)

    def dirty_range(self) -> tuple[int, int]:
        """返回自上次 ``clear_dirty()`` 以来内容变化的行区间（右开）。

        行索引按当前行表计；滚动淘汰只会改变索引，内容未变的行不算脏。
        """
        if self._dirty_from is None or self._dirty_from >= self._dirty_to:
            return (0, 0)
        return self._dirty_from, self._dirty_to

    def clear_dirty(self) -> None:
        """由渲染方在完成一帧渲染后清除内容变化标记。"""
        self._dirty_from = None
        self._dirty_to = 0

    def _touch(self, row: int) -> None:
        """标记单行内容变化，越界行按区间并集累积。"""
        if self._dirty_from is None or self._dirty_from >= self._dirty_to or row < self._dirty_from:
            self._dirty_from = row
        self._dirty_to = max(self._dirty_to, row + 1)

    def text_lines(self) -> tuple[str, ...]:
        """返回按字符拼接后的纯文本行，便于测试与诊断。"""
        return tuple("".join(cell.char for cell in row) for row in self._rows)

    def reset(self) -> None:
        """清空画面、样式与解析状态。"""
        self._rows = [[]]
        self._row_times = [None]
        self._cursor_row = 0
        self._cursor_col = 0
        self._style = DEFAULT_STYLE
        self._pending = ""
        self._dropped = 0
        self._dirty_from = 0
        self._dirty_to = len(self._rows)

    def feed(self, text: str, *, timestamp: datetime | None = None) -> None:
        """解析一段接收文本，未完成的转义序列留待下次拼接。

        ``timestamp`` 作为本次写入行的“首次出现时间”记录到行元数据，供渲染方
        按需显示行级时间；已写入的行不会被后续写入覆盖时间。
        """
        if timestamp is not None and not isinstance(timestamp, datetime):
            raise ValidationError("终端行时间必须是 datetime 或 None。")
        if not text:
            return
        self._active_time = timestamp
        buffer = self._pending + text
        self._pending = ""
        index = 0
        length = len(buffer)
        while index < length:
            char = buffer[index]
            if char == "\x1b":
                consumed = self._consume_escape(buffer, index)
                if consumed is None:
                    self._pending = buffer[index:]
                    break
                index = consumed
            elif char == "\r":
                self._cursor_col = 0
                index += 1
            elif char == "\n":
                self._line_feed()
                index += 1
            elif char == "\b":
                self._cursor_col = max(0, self._cursor_col - 1)
                index += 1
            elif char == "\t":
                self._tab()
                index += 1
            elif char < " " or char == "\x7f":
                index += 1
            else:
                self._write_char(char)
                index += 1
        self._trim()

    def _write_char(self, char: str) -> None:
        if combining(char):
            self._attach_combining(char)
            return
        width = _WIDE_WIDTH if east_asian_width(char) in _WIDE_CATEGORIES else 1
        if self._cursor_col + width > self._max_columns:
            self._cursor_col = 0
            self._line_feed()
        self._put(self._cursor_row, self._cursor_col, TerminalCell(char=char, style=self._style))
        if width == _WIDE_WIDTH:
            self._put(
                self._cursor_row,
                self._cursor_col + 1,
                TerminalCell(char="", style=self._style, trailing=True),
            )
        self._cursor_col += width
        if self._cursor_col >= self._max_columns:
            self._cursor_col = 0
            self._line_feed()

    def _attach_combining(self, char: str) -> None:
        row = self._rows[self._cursor_row]
        for position in range(len(row) - 1, -1, -1):
            if not row[position].trailing:
                row[position] = replace(row[position], char=row[position].char + char)
                self._touch(self._cursor_row)
                return

    def _put(self, row: int, column: int, cell: TerminalCell) -> None:
        self._ensure_row(row)
        line = self._rows[row]
        if self._row_times[row] is None:
            self._row_times[row] = self._active_time
        while len(line) <= column:
            line.append(TerminalCell())
        line[column] = cell
        self._touch(row)

    def _ensure_row(self, row: int) -> None:
        while len(self._rows) <= row:
            self._rows.append([])
            self._row_times.append(None)

    def _line_feed(self) -> None:
        self._cursor_row += 1
        self._cursor_col = 0
        self._ensure_row(self._cursor_row)

    def _tab(self) -> None:
        target = (self._cursor_col // TAB_WIDTH + 1) * TAB_WIDTH
        self._cursor_col = min(target, self._max_columns - 1)

    def _trim(self) -> None:
        excess = len(self._rows) - self._max_rows
        if excess <= 0:
            return
        del self._rows[:excess]
        del self._row_times[:excess]
        self._dropped += excess
        self._cursor_row = max(0, self._cursor_row - excess)
        if self._dirty_from is not None:
            # 行索引整体前移；被淘汰区间里的脏行并入区间头。
            self._dirty_from = max(0, self._dirty_from - excess)
            self._dirty_to = max(0, self._dirty_to - excess)

    def _consume_escape(self, buffer: str, index: int) -> int | None:
        if index + 1 >= len(buffer):
            return None
        if buffer[index + 1] != "[":
            return index + 2
        return self._consume_csi(buffer, index)

    def _consume_csi(self, buffer: str, index: int) -> int | None:
        position = index + 2
        parameter_start = position
        while (
            position < len(buffer)
            and _CSI_PARAMETER_MIN <= ord(buffer[position]) <= _CSI_PARAMETER_MAX
        ):
            position += 1
        parameter_end = position
        while (
            position < len(buffer)
            and _CSI_INTERMEDIATE_MIN <= ord(buffer[position]) <= _CSI_INTERMEDIATE_MAX
        ):
            position += 1
        if position >= len(buffer):
            return None
        if position == parameter_end:
            parameters = buffer[parameter_start:parameter_end]
            if parameters[:1] not in _PRIVATE_MARKERS:
                self._apply_csi(parameters, buffer[position])
        return position + 1

    @staticmethod
    def _parse_params(text: str) -> list[int] | None:
        if not text:
            return []
        values: list[int] = []
        for part in text.split(";"):
            if part == "":
                values.append(0)
            elif part.isdigit():
                values.append(int(part))
            else:
                return None
        return values

    @staticmethod
    def _amount(values: list[int], index: int, default: int) -> int:
        if index < len(values) and values[index] > 0:
            return values[index]
        return default

    def _apply_csi(self, parameters: str, final: str) -> None:
        values = self._parse_params(parameters)
        if values is None:
            return
        if final == "m":
            self._style = self._style.apply_sgr(values or [0])
        elif final == "A":
            self._cursor_row = max(0, self._cursor_row - self._amount(values, 0, 1))
        elif final == "B":
            self._cursor_row += self._amount(values, 0, 1)
            self._ensure_row(self._cursor_row)
        elif final == "C":
            self._cursor_col = min(
                self._max_columns - 1,
                self._cursor_col + self._amount(values, 0, 1),
            )
        elif final == "D":
            self._cursor_col = max(0, self._cursor_col - self._amount(values, 0, 1))
        elif final in {"H", "f"}:
            row = max(0, self._amount(values, 0, 1) - 1)
            column = max(0, self._amount(values, 1, 1) - 1)
            self._cursor_row = row
            self._cursor_col = min(column, self._max_columns - 1)
            self._ensure_row(row)
        elif final == "G":
            self._cursor_col = min(self._amount(values, 0, 1) - 1, self._max_columns - 1)
            self._cursor_col = max(0, self._cursor_col)
        elif final == "J":
            self._erase_display(values[0] if values else 0)
        elif final == "K":
            self._erase_line(values[0] if values else 0)

    def _erase_display(self, mode: int) -> None:
        if mode == _ERASE_ALL:
            self.reset()
        elif mode == _ERASE_TO_START:
            for row in range(self._cursor_row):
                self._rows[row] = []
                self._touch(row)
            self._clear_cells(self._cursor_row, 0, self._cursor_col + 1)
        elif mode == _ERASE_TO_END:
            self._clear_cells(self._cursor_row, self._cursor_col, self._max_columns)
            del self._rows[self._cursor_row + 1 :]
            del self._row_times[self._cursor_row + 1 :]

    def _erase_line(self, mode: int) -> None:
        if mode == _ERASE_ALL:
            self._clear_cells(self._cursor_row, 0, self._max_columns)
        elif mode == _ERASE_TO_START:
            self._clear_cells(self._cursor_row, 0, self._cursor_col + 1)
        else:
            self._clear_cells(self._cursor_row, self._cursor_col, self._max_columns)

    def _clear_cells(self, row: int, start: int, end: int) -> None:
        self._ensure_row(row)
        line = self._rows[row]
        for column in range(max(start, 0), min(end, self._max_columns)):
            if column < len(line):
                line[column] = TerminalCell()
        self._touch(row)
