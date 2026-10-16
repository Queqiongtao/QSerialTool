"""接收区分栏视图的记录显示格式化纯函数。"""

from qserialtool.domain import DisplayMode, LogRecord
from qserialtool.ui.terminal_render_format import format_timestamp
from qserialtool.ui.theme_manager import data_colors


def timestamp_prefix(record: LogRecord) -> str:
    """返回记录时间戳前缀，格式与终端行时间戳一致。"""
    return format_timestamp(record.timestamp_utc)


def payload_text(record: LogRecord, display_mode: DisplayMode) -> str:
    """按当前显示模式返回记录正文（HEX 或文本）。"""
    return record.hex_text if display_mode == "hex" else record.text


def format_record(
    record: LogRecord,
    *,
    show_timestamp: bool,
    display_mode: DisplayMode,
) -> str:
    """把一条记录整体格式化为“时间戳 + 方向 + 正文”，供 SYSTEM 行使用。"""
    prefix = timestamp_prefix(record) if show_timestamp else ""
    prefix += f"{record.direction.upper()}: "
    return prefix + payload_text(record, display_mode)


def color_for(record: LogRecord) -> str:
    """返回记录方向对应的主题色。"""
    colors = data_colors()
    if record.direction == "rx":
        return colors.rx
    if record.direction == "tx":
        return colors.tx
    return colors.system


def record_segments(
    record: LogRecord,
    *,
    show_timestamp: bool,
    display_mode: DisplayMode,
) -> tuple[tuple[str, str, bool], ...]:
    """拆分一行记录：时间戳弱化、方向前缀着色加粗、正文用默认文本色。"""
    colors = data_colors()
    if record.direction not in ("rx", "tx"):
        return (
            (
                format_record(record, show_timestamp=show_timestamp, display_mode=display_mode),
                colors.system,
                False,
            ),
        )
    segments: list[tuple[str, str, bool]] = []
    if show_timestamp:
        segments.append((timestamp_prefix(record), colors.system, False))
    segments.append((f"{record.direction.upper()}: ", color_for(record), True))
    segments.append((payload_text(record, display_mode), colors.text, False))
    return tuple(segments)


def should_show(record: LogRecord, *, show_rx: bool, show_tx: bool) -> bool:
    """按 RX/TX 勾选状态判断记录是否参与分栏显示。"""
    if record.direction == "rx":
        return show_rx
    if record.direction == "tx":
        return show_tx
    return True
