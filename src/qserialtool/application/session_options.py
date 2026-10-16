"""会话控制器的可选参数与输入校验。"""

from collections.abc import Callable
from dataclasses import dataclass

from qserialtool.application.serial_worker import SerialWorkerOptions
from qserialtool.domain import (
    LogFormat,
    LogRecord,
    LogSink,
    RecordBuffer,
    SessionSnapshot,
    ValidationError,
)

SnapshotCallback = Callable[[SessionSnapshot], None]
RecordCallback = Callable[[LogRecord], None]

MAX_SESSION_TITLE_LENGTH = 40


@dataclass(frozen=True, slots=True)
class SessionControllerOptions:
    """SessionController 的可选身份、缓冲和回调参数。"""

    session_id: str | None = None
    title: str | None = None
    buffer: RecordBuffer | None = None
    on_snapshot: SnapshotCallback | None = None
    on_record: RecordCallback | None = None
    worker_options: SerialWorkerOptions | None = None
    log_sink_factory: Callable[[LogFormat], LogSink] | None = None
    auto_log_enabled: bool = False
    auto_log_format: LogFormat = "csv"
    auto_log_directory: str = ""


def validate_session_title(title: str) -> str:
    """校验并返回清理后的会话标题。"""
    cleaned = title.strip()
    if not cleaned:
        raise ValidationError("会话名称不能为空。")
    if len(cleaned) > MAX_SESSION_TITLE_LENGTH:
        raise ValidationError(f"会话名称不能超过 {MAX_SESSION_TITLE_LENGTH} 个字符。")
    return cleaned
