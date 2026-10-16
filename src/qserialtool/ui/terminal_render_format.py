"""终端单元格的着色格式、时间前缀与高亮叠加。"""

from datetime import datetime

from PySide6.QtGui import QColor, QFont, QPalette, QTextCharFormat

from qserialtool.domain import TerminalCell, TerminalStyle
from qserialtool.ui.terminal_highlight import find_highlights
from qserialtool.ui.theme_manager import ansi_color, highlight_colors


def format_timestamp(moment: datetime) -> str:
    """按分栏时间戳的同一格式渲染本地时间前缀。"""
    local_time = moment.astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return f"[{local_time}] "


def text_format(color: str, bold: bool = False) -> QTextCharFormat:
    """返回按颜色与加粗生成的字符格式。"""
    text_format = QTextCharFormat()
    text_format.setForeground(QColor(color))
    if bold:
        text_format.setFontWeight(QFont.Weight.Bold)
    return text_format


def style_format(
    style: TerminalStyle,
    override: str | None,
    palette: QPalette,
) -> QTextCharFormat:
    """按 ANSI 样式与可选覆盖色生成字符格式。"""
    text_format = QTextCharFormat()
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


def highlight_overrides(row: tuple[TerminalCell, ...]) -> dict[int, str]:
    """按行文本匹配地址与链接，返回需要改色的单元格索引到颜色。"""
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
