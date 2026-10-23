"""CSV 串口日志输出。"""

import csv
from pathlib import Path
from types import TracebackType
from typing import TextIO

from qserialtool.domain import LogIOError, LogRecord

CSV_FIELDS = ("timestamp", "direction", "encoding", "text", "hex")


class _CountingTextStream:
    """包装文本流并统计 UTF-8 编码后的写入字节数。"""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self.bytes_written = 0

    def write(self, text: str) -> int:
        written = self._stream.write(text)
        self.bytes_written += len(text.encode("utf-8"))
        return written


class CsvLogSink:
    """把一个会话的日志写成 RFC 4180 CSV。"""

    def __init__(self) -> None:
        self._stream: TextIO | None = None
        self._counter: _CountingTextStream | None = None
        self._writer: csv.DictWriter[str] | None = None
        self._bytes_written = 0

    def open(self, path: Path) -> None:
        """创建并打开 CSV 文件。"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = path.open("w", encoding="utf-8-sig", newline="")
            self._counter = _CountingTextStream(self._stream)
            self._writer = csv.DictWriter(self._counter, fieldnames=CSV_FIELDS)
            self._writer.writeheader()
            self._bytes_written = self._counter.bytes_written
        except OSError as exc:
            raise LogIOError(f"无法打开 CSV 日志：{exc}") from exc

    def write(self, record: LogRecord) -> None:
        """写入一条不可变日志记录。"""
        if self._writer is None or self._counter is None:
            raise LogIOError("CSV 日志尚未打开。")
        try:
            self._writer.writerow(
                {
                    "timestamp": record.timestamp_utc.astimezone().isoformat(
                        timespec="milliseconds"
                    ),
                    "direction": record.direction.upper(),
                    "encoding": record.encoding,
                    "text": record.text,
                    "hex": record.hex_text,
                }
            )
            self._bytes_written = self._counter.bytes_written
        except (OSError, csv.Error) as exc:
            raise LogIOError(f"CSV 日志写入失败：{exc}") from exc

    @property
    def bytes_written(self) -> int:
        """返回当前 CSV 文件已写入的 UTF-8 字节数（含表头）。"""
        return self._bytes_written

    def flush(self) -> None:
        """刷新 CSV 缓冲。"""
        if self._stream is None:
            return
        try:
            self._stream.flush()
        except OSError as exc:
            raise LogIOError(f"CSV 日志刷新失败：{exc}") from exc

    def close(self) -> None:
        """关闭 CSV 文件。"""
        if self._stream is not None:
            try:
                self._stream.close()
            finally:
                self._stream = None
                self._counter = None
                self._writer = None

    def __enter__(self) -> "CsvLogSink":
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
