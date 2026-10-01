"""测试 Port 协议的结构化契约。"""

from datetime import datetime, timezone
from pathlib import Path

from qserialtool.domain import (
    AppConfig,
    Clock,
    ConfigStore,
    LogRecord,
    LogSink,
    SerialConfig,
    Transport,
)


class FakeTransport:
    def open(self, config: SerialConfig) -> None:
        self.config = config

    def close(self, timeout: float) -> None:
        self.timeout = timeout

    def read(self, max_bytes: int, timeout: float) -> bytes:
        return b""

    def write_all(self, data: bytes, timeout: float) -> None:
        self.data = data

    def set_line_state(self, *, dtr: bool, rts: bool) -> None:
        self.dtr = dtr
        self.rts = rts

    @property
    def is_open(self) -> bool:
        return True


class FakeClock:
    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return 0.0


class FakeConfigStore:
    def load(self) -> AppConfig | None:
        return None

    def save(self, config: AppConfig) -> None:
        self.config = config


class FakeLogSink:
    def open(self, path: Path) -> None:
        self.path = path

    def write(self, record: LogRecord) -> None:
        self.record = record

    def flush(self) -> None:
        self.flushed = True

    def close(self) -> None:
        self.closed = True


def test_protocols_support_runtime_structural_checks() -> None:
    assert isinstance(FakeTransport(), Transport)
    assert isinstance(FakeClock(), Clock)
    assert isinstance(FakeConfigStore(), ConfigStore)
    assert isinstance(FakeLogSink(), LogSink)
