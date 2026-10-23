"""人类可读 TXT 串口日志输出。"""

from pathlib import Path
from types import TracebackType
from typing import TextIO

from qserialtool.domain import LogIOError, LogRecord


class TxtLogSink:
    """把一个会话的日志写成 UTF-8 文本。"""

    def __init__(self) -> None:
        self._stream: TextIO | None = None
        self._bytes_written = 0

    def open(self, path: Path) -> None:
        """创建并打开文本日志。"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = path.open("w", encoding="utf-8", newline="\n")
            self._bytes_written = 0
        except OSError as exc:
            raise LogIOError(f"无法打开文本日志：{exc}") from exc

    def write(self, record: LogRecord) -> None:
        """写入一条记录。"""
        if self._stream is None:
            raise LogIOError("文本日志尚未打开。")
        local_time = record.timestamp_utc.astimezone().isoformat(timespec="milliseconds")
        prefix = f"[{local_time}] {record.direction.upper()} [{record.encoding.upper()}]"
        line = f"{prefix} {record.text}\n"
        try:
            self._stream.write(line)
        except OSError as exc:
            raise LogIOError(f"文本日志写入失败：{exc}") from exc
        self._bytes_written += len(line.encode("utf-8"))

    @property
    def bytes_written(self) -> int:
        """返回当前文本文件已写入的 UTF-8 字节数。"""
        return self._bytes_written

    def flush(self) -> None:
        """刷新文本缓冲。"""
        if self._stream is None:
            return
        try:
            self._stream.flush()
        except OSError as exc:
            raise LogIOError(f"文本日志刷新失败：{exc}") from exc

    def close(self) -> None:
        """关闭文本日志。"""
        if self._stream is not None:
            try:
                self._stream.close()
            finally:
                self._stream = None

    def __enter__(self) -> "TxtLogSink":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
