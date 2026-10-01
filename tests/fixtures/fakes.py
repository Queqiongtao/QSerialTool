"""无硬件、可注入时钟和传输测试替身。"""

from collections import deque
from datetime import datetime, timedelta, timezone
from threading import Condition, Event, Lock
from time import monotonic

from qserialtool.domain import DomainError, SerialConfig


class FakeClock:
    """可手动推进的确定性时钟。"""

    def __init__(
        self,
        *,
        now_utc: datetime | None = None,
        monotonic_value: float = 100.0,
    ) -> None:
        self._now_utc = now_utc or datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
        self._monotonic = monotonic_value

    def now_utc(self) -> datetime:
        return self._now_utc

    def monotonic(self) -> float:
        return self._monotonic

    def advance(self, seconds: float) -> None:
        self._monotonic += seconds
        self._now_utc += timedelta(seconds=seconds)


class FakeTransport:
    """线程安全的 Transport 测试替身。"""

    def __init__(  # noqa: PLR0913
        self,
        *,
        open_error: BaseException | None = None,
        read_error: BaseException | None = None,
        write_error: BaseException | None = None,
        line_error: BaseException | None = None,
        reads: list[bytes] | None = None,
        close_on_read: bool = False,
        close_error: BaseException | None = None,
    ) -> None:
        self.open_error = open_error
        self.read_error = read_error
        self.write_error = write_error
        self.line_error = line_error
        self.close_on_read = close_on_read
        self.close_error = close_error
        self._reads = deque(reads or [])
        self._condition = Condition()
        self._is_open = False
        self._lock = Lock()
        self.config: SerialConfig | None = None
        self.writes: list[bytes] = []
        self.line_states: list[tuple[bool, bool]] = []
        self.read_timeouts: list[float] = []
        self.open_count = 0
        self.close_count = 0
        self.opened_event = Event()
        self.closed_event = Event()
        self.write_event = Event()
        self.receive_event = Event()
        self.line_event = Event()

    def open(self, config: SerialConfig) -> None:
        if self.open_error is not None:
            raise self.open_error
        with self._condition:
            self.config = config
            self._is_open = True
            self.open_count += 1
            self._condition.notify_all()
        self.opened_event.set()

    def close(self, timeout: float) -> None:
        if self.close_error is not None:
            raise self.close_error
        with self._condition:
            self._is_open = False
            self.close_count += 1
            self._condition.notify_all()
        self.closed_event.set()

    def read(self, max_bytes: int, timeout: float) -> bytes:
        with self._condition:
            self.read_timeouts.append(timeout)
            deadline = monotonic() + timeout
            while self._is_open and not self._reads and self.read_error is None:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return b""
                self._condition.wait(remaining)
            if self.read_error is not None:
                raise self.read_error
            if not self._is_open or not self._reads:
                return b""
            data = self._reads.popleft()
            if self.close_on_read and not self._reads:
                self._is_open = False
                self._condition.notify_all()
        self.receive_event.set()
        return data[:max_bytes]

    def write_all(self, data: bytes, timeout: float) -> None:
        if self.write_error is not None:
            raise self.write_error
        with self._lock:
            if not self._is_open:
                raise RuntimeError("transport closed")
            self.writes.append(data)
        self.write_event.set()

    def set_line_state(self, *, dtr: bool, rts: bool) -> None:
        if self.line_error is not None:
            raise self.line_error
        with self._lock:
            self.line_states.append((dtr, rts))
        self.line_event.set()

    @property
    def is_open(self) -> bool:
        with self._condition:
            return self._is_open

    def push_read(self, data: bytes) -> None:
        with self._condition:
            self._reads.append(data)
            self._condition.notify_all()


class RecordingWorkerHandler:
    """记录 Worker 事件并提供同步等待点。"""

    def __init__(self) -> None:
        self.opened_event = Event()
        self.open_failed_event = Event()
        self.received_event = Event()
        self.sent_event = Event()
        self.io_error_event = Event()
        self.stopped_event = Event()
        self.opened_config: SerialConfig | None = None
        self.open_error: DomainError | None = None
        self.received: list[bytes] = []
        self.sent: list[bytes] = []
        self.io_errors: list[DomainError] = []
        self._lock = Lock()

    def on_opened(self, config: SerialConfig) -> None:
        with self._lock:
            self.opened_config = config
        self.opened_event.set()

    def on_open_failed(self, error: DomainError) -> None:
        with self._lock:
            self.open_error = error
        self.open_failed_event.set()

    def on_bytes_received(self, data: bytes) -> None:
        with self._lock:
            self.received.append(data)
        self.received_event.set()

    def on_bytes_sent(self, data: bytes) -> None:
        with self._lock:
            self.sent.append(data)
        self.sent_event.set()

    def on_io_error(self, error: DomainError) -> None:
        with self._lock:
            self.io_errors.append(error)
        self.io_error_event.set()

    def on_stopped(self) -> None:
        self.stopped_event.set()
