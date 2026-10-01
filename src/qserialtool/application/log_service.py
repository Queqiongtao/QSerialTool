"""自动日志文件生命周期和写入策略。"""

import re
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from qserialtool.domain import Clock, DomainError, LogFormat, LogIOError, LogRecord, LogSink

DEFAULT_FLUSH_INTERVAL_SECONDS = 1.0
DEFAULT_FLUSH_BYTES = 256 * 1024
_INVALID_FILENAME_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def default_log_directory() -> Path:
    """返回跨平台默认日志目录。"""
    return Path.home() / "Documents" / "QSerialTool" / "Logs"


def sanitize_port_name(port: str, *, max_length: int = 48) -> str:
    """清理端口名中的文件系统非法字符和路径分隔符。"""
    cleaned = _INVALID_FILENAME_CHARACTERS.sub("_", port).strip(" ._")
    if not cleaned:
        return "unknown-port"
    return cleaned[:max_length]


class LogService:
    """管理一个会话从连接到断开之间的日志文件。"""

    def __init__(
        self,
        *,
        sink_factory: Callable[[LogFormat], LogSink],
        clock: Clock,
        flush_interval_seconds: float = DEFAULT_FLUSH_INTERVAL_SECONDS,
        flush_bytes: int = DEFAULT_FLUSH_BYTES,
    ) -> None:
        if not callable(sink_factory):
            raise LogIOError("日志输出工厂必须可调用。")
        if flush_interval_seconds <= 0:
            raise LogIOError("日志刷新间隔必须大于零。")
        if type(flush_bytes) is not int or flush_bytes <= 0:
            raise LogIOError("日志刷新字节数必须是正整数。")
        self._sink_factory = sink_factory
        self._clock = clock
        self._flush_interval_seconds = flush_interval_seconds
        self._flush_bytes = flush_bytes
        self._sink: LogSink | None = None
        self.path: Path | None = None
        self._last_flush = clock.monotonic()
        self._bytes_since_flush = 0

    @property
    def is_active(self) -> bool:
        """返回日志文件是否已打开。"""
        return self._sink is not None

    def start(self, *, directory: str, port: str, log_format: LogFormat) -> Path:
        """创建新日志文件并打开对应输出。"""
        self.close()
        selected_directory = (
            Path(directory).expanduser() if directory.strip() else default_log_directory()
        )
        try:
            selected_directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise LogIOError(f"无法创建日志目录：{exc}") from exc
        timestamp = self._clock.now_utc().astimezone().strftime("%Y%m%d_%H%M%S")
        extension = "csv" if log_format == "csv" else "txt"
        base_name = f"QSerialTool_{sanitize_port_name(port)}_{timestamp}"
        path = selected_directory / f"{base_name}.{extension}"
        suffix = 1
        while path.exists():
            path = selected_directory / f"{base_name}_{suffix}.{extension}"
            suffix += 1
        sink = self._sink_factory(log_format)
        try:
            sink.open(path)
        except DomainError:
            raise
        except OSError as exc:
            raise LogIOError(f"无法打开日志文件：{exc}") from exc
        self._sink = sink
        self.path = path
        self._last_flush = self._clock.monotonic()
        self._bytes_since_flush = 0
        return path

    def write(self, record: LogRecord) -> None:
        """写入记录并按时间或字节数周期性刷新。"""
        sink = self._sink
        if sink is None:
            return
        try:
            sink.write(record)
            self._bytes_since_flush += len(record.raw)
            elapsed = self._clock.monotonic() - self._last_flush
            if (
                self._bytes_since_flush >= self._flush_bytes
                or elapsed >= self._flush_interval_seconds
            ):
                sink.flush()
                self._last_flush = self._clock.monotonic()
                self._bytes_since_flush = 0
        except DomainError:
            self._disable()
            raise
        except OSError as exc:
            self._disable()
            raise LogIOError(f"日志写入失败：{exc}") from exc

    def flush(self) -> None:
        """立即刷新当前日志。"""
        sink = self._sink
        if sink is None:
            return
        try:
            sink.flush()
        except DomainError:
            self._disable()
            raise
        except OSError as exc:
            self._disable()
            raise LogIOError(f"日志刷新失败：{exc}") from exc

    def close(self) -> None:
        """刷新并关闭当前日志。"""
        sink = self._sink
        if sink is None:
            return
        self._sink = None
        try:
            sink.flush()
        except DomainError:
            raise
        except OSError as exc:
            raise LogIOError(f"日志刷新失败：{exc}") from exc
        finally:
            try:
                sink.close()
            except DomainError:
                if not self._sink and self.path is not None:
                    raise
            except OSError as exc:
                raise LogIOError(f"日志关闭失败：{exc}") from exc

    def _disable(self) -> None:
        sink = self._sink
        self._sink = None
        if sink is not None:
            with suppress(DomainError):
                sink.close()
