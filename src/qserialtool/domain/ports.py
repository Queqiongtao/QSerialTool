"""领域层依赖的外部能力协议。"""

from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import AppConfig, LogRecord, SerialConfig


@runtime_checkable
class Transport(Protocol):
    """串口传输能力，方法由所属工作线程独占调用。"""

    def open(self, config: SerialConfig) -> None:
        """使用给定参数打开串口。"""
        ...

    def close(self, timeout: float) -> None:
        """在超时时间内关闭串口。"""
        ...

    def read(self, max_bytes: int, timeout: float) -> bytes:
        """读取最多 max_bytes 个字节，超时返回空字节。"""
        ...

    def write_all(self, data: bytes, timeout: float) -> None:
        """完整写入数据，失败时抛出传输错误。"""
        ...

    def set_line_state(self, *, dtr: bool, rts: bool) -> None:
        """设置 DTR 和 RTS 线路状态。"""
        ...

    @property
    def is_open(self) -> bool:
        """返回底层串口是否已打开。"""
        ...


@runtime_checkable
class PortScanner(Protocol):
    """系统串口发现能力。"""

    def list_ports(self) -> tuple[str, ...]:
        """返回当前可用的串口名称。"""
        ...


@runtime_checkable
class Clock(Protocol):
    """可注入的时钟能力。"""

    def now_utc(self) -> datetime:
        """返回包含时区信息的 UTC 当前时间。"""
        ...

    def monotonic(self) -> float:
        """返回用于时间间隔计算的单调秒数。"""
        ...


@runtime_checkable
class ConfigStore(Protocol):
    """应用配置持久化能力。"""

    def load(self) -> AppConfig | None:
        """加载配置，不存在时返回 None。"""
        ...

    def save(self, config: AppConfig) -> None:
        """持久化完整应用配置。"""
        ...


@runtime_checkable
class LogSink(Protocol):
    """串口日志输出能力。"""

    def open(self, path: Path) -> None:
        """打开日志文件。"""
        ...

    def write(self, record: LogRecord) -> None:
        """写入一条记录。"""
        ...

    def flush(self) -> None:
        """刷新尚未落盘的数据。"""
        ...

    def close(self) -> None:
        """关闭日志输出。"""
        ...
