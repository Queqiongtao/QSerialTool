"""终端单元格样式与 SGR 参数解析。"""

from dataclasses import dataclass, replace

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
