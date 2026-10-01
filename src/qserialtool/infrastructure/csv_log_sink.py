"""CSV 串口日志输出。"""

import csv
from pathlib import Path
from types import TracebackType
from typing import TextIO

from qserialtool.domain import LogIOError, LogRecord

CSV_FIELDS = ("timestamp", "direction", "encoding", "text", "hex")


class CsvLogSink:
    """把一个会话的日志写成 RFC 4180 CSV。"""

    def __init__(self) -> None:
        self._stream: TextIO | None = None
        self._writer: csv.DictWriter[str] | None = None

    def open(self, path: Path) -> None:
        """创建并打开 CSV 文件。"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = path.open("w", encoding="utf-8-sig", newline="")
            self._writer = csv.DictWriter(self._stream, fieldnames=CSV_FIELDS)
            self._writer.writeheader()
        except OSError as exc:
            raise LogIOError(f"无法打开 CSV 日志：{exc}") from exc

    def write(self, record: LogRecord) -> None:
        """写入一条不可变日志记录。"""
        if self._writer is None:
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
        except (OSError, csv.Error) as exc:
            raise LogIOError(f"CSV 日志写入失败：{exc}") from exc

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
