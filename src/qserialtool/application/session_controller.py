"""单标签串口会话的应用层编排。"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from uuid import uuid4

from qserialtool.application.log_service import LogService
from qserialtool.application.serial_worker import (
    SerialWorker,
    SerialWorkerOptions,
    WorkerEventHandler,
)
from qserialtool.domain import (
    Clock,
    DomainError,
    InvalidStateTransitionError,
    LogFormat,
    LogIOError,
    LogRecord,
    LogSink,
    RecordBuffer,
    SerialConfig,
    SessionSnapshot,
    SessionState,
    SessionStateMachine,
    Transport,
    TransportIOError,
    UserFacingError,
    ValidationError,
)

SnapshotCallback = Callable[[SessionSnapshot], None]
RecordCallback = Callable[[LogRecord], None]


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


class SessionController(WorkerEventHandler):
    """维护单个串口会话的状态、缓冲和 Worker 生命周期。"""

    def __init__(
        self,
        *,
        config: SerialConfig,
        transport_factory: Callable[[], Transport],
        clock: Clock,
        options: SessionControllerOptions | None = None,
    ) -> None:
        if not callable(transport_factory):
            raise ValidationError("transport_factory 必须可调用。")
        selected_options = options or SessionControllerOptions()
        self._lock = RLock()
        self._session_id = selected_options.session_id or uuid4().hex
        if not self._session_id.strip():
            raise ValidationError("会话 ID 不能为空。")
        self._title = selected_options.title or config.port or "未选择端口"
        if not self._title.strip():
            raise ValidationError("会话标题不能为空。")
        self._config = config
        self._transport_factory = transport_factory
        self._clock = clock
        self._worker_options = selected_options.worker_options
        self._log_sink_factory = selected_options.log_sink_factory
        self._auto_log_enabled = selected_options.auto_log_enabled
        self._auto_log_format = selected_options.auto_log_format
        self._auto_log_directory = selected_options.auto_log_directory
        self._log_service = (
            LogService(sink_factory=self._log_sink_factory, clock=self._clock)
            if self._log_sink_factory is not None
            else None
        )
        self._buffer = selected_options.buffer or RecordBuffer()
        self._state_machine = SessionStateMachine()
        self._worker: SerialWorker | None = None
        self._last_error: UserFacingError | None = None
        self._rx_bytes = 0
        self._tx_bytes = 0
        self._on_snapshot = selected_options.on_snapshot
        self._on_record = selected_options.on_record
        self._notify_current_snapshot()

    @property
    def session_id(self) -> str:
        """返回稳定会话 ID。"""
        return self._session_id

    @property
    def title(self) -> str:
        """返回标签标题。"""
        return self._title

    @property
    def config(self) -> SerialConfig:
        """返回当前连接配置。"""
        return self._config

    @property
    def state(self) -> SessionState:
        """返回当前会话状态。"""
        with self._lock:
            return self._state_machine.state

    @property
    def snapshot(self) -> SessionSnapshot:
        """返回线程安全的只读状态快照。"""
        with self._lock:
            return self._build_snapshot()

    @property
    def records(self) -> tuple[LogRecord, ...]:
        """返回当前内存缓冲的不可变快照。"""
        with self._lock:
            return self._buffer.records

    @property
    def auto_log_enabled(self) -> bool:
        """返回自动日志开关。"""
        return self._auto_log_enabled

    @property
    def auto_log_format(self) -> LogFormat:
        """返回自动日志格式。"""
        return self._auto_log_format

    @property
    def auto_log_directory(self) -> str:
        """返回自动日志目录。"""
        return self._auto_log_directory

    @property
    def log_path(self) -> object | None:
        """返回当前连接正在写入的日志路径。"""
        service = self._log_service
        return service.path if service is not None else None

    def update_log_preferences(
        self, *, enabled: bool, log_format: LogFormat, directory: str
    ) -> None:
        """更新下一次连接使用的自动日志设置。"""
        if type(enabled) is not bool:
            raise ValidationError("自动日志开关必须是布尔值。")
        if self._state_machine.state in {
            SessionState.CONNECTING,
            SessionState.CONNECTED,
            SessionState.DISCONNECTING,
        }:
            raise InvalidStateTransitionError(self._state_machine.state, "update_log_preferences")
        if log_format not in {"csv", "txt"}:
            raise ValidationError("自动日志格式必须是 csv 或 txt。")
        if not isinstance(directory, str):
            raise ValidationError("自动日志开关必须是布尔值。")
        self._auto_log_enabled = enabled
        self._auto_log_format = log_format
        self._auto_log_directory = directory

    def export_records(self, path: Path, log_format: LogFormat) -> int:
        """把当前完整内存缓冲导出为 CSV 或 TXT。"""
        if self._log_sink_factory is None:
            raise LogIOError("未配置日志输出。")
        if log_format not in {"csv", "txt"}:
            raise ValidationError("日志格式必须是 csv 或 txt。")
        records = self.records
        sink = self._log_sink_factory(log_format)
        try:
            sink.open(path)
            for record in records:
                sink.write(record)
            sink.flush()
        finally:
            sink.close()
        return len(records)

    def connect(self, config: SerialConfig | None = None) -> None:
        """校验配置并启动串口 Worker。"""
        selected_config = config or self._config
        selected_config.validate_for_connect()
        with self._lock:
            if self._worker is not None and self._worker.is_alive:
                raise InvalidStateTransitionError(
                    self._state_machine.state,
                    "connect",
                    SessionState.CONNECTING,
                )
            self._config = selected_config
            self._last_error = None
            self._state_machine.connect()
            worker = SerialWorker(
                config=selected_config,
                transport_factory=self._transport_factory,
                event_handler=self,
                options=self._worker_options,
            )
            self._worker = worker
            snapshot = self._build_snapshot()
        self._notify_snapshot(snapshot)
        worker.start()

    def disconnect(self, timeout: float = 1.5) -> bool:
        """请求 Worker 停止、关闭端口并等待清理。"""
        if timeout <= 0:
            raise ValidationError("断开超时必须大于零。")
        with self._lock:
            if self._state_machine.state in {SessionState.DISCONNECTED, SessionState.CLOSED}:
                return True
            if self._state_machine.state is SessionState.CONNECTING:
                raise InvalidStateTransitionError(
                    self._state_machine.state,
                    "disconnect",
                    SessionState.DISCONNECTING,
                )
            if self._state_machine.state is SessionState.CONNECTED:
                self._state_machine.begin_disconnect()
                snapshot = self._build_snapshot()
            else:
                snapshot = None
            worker = self._worker
        if snapshot is not None:
            self._notify_snapshot(snapshot)
        if worker is not None:
            worker.request_stop()
            stopped = worker.join(timeout)
            if not stopped:
                with self._lock:
                    if self._state_machine.state is SessionState.DISCONNECTING:
                        self._state_machine.mark_cleanup_failed()
                    self._last_error = TransportIOError("等待串口线程退出超时。").to_user_facing()
                    error_snapshot = self._build_snapshot()
                self._notify_snapshot(error_snapshot)
                return False
        with self._lock:
            if self._state_machine.state is SessionState.DISCONNECTING:
                self._state_machine.mark_disconnected()
            snapshot = self._build_snapshot()
        self._notify_snapshot(snapshot)
        return True

    def close(self, *, force: bool = False) -> None:
        """关闭标签状态；活动会话需要显式强制关闭。"""
        with self._lock:
            state = self._state_machine.state
        if state in {SessionState.CONNECTED, SessionState.CONNECTING, SessionState.DISCONNECTING}:
            if not force:
                raise InvalidStateTransitionError(state, "close", SessionState.CLOSED)
            worker = self._worker
            if worker is not None:
                worker.request_stop()
                worker.join(1.5)
        with self._lock:
            self._state_machine.close(force=force)
            self._worker = None
            snapshot = self._build_snapshot()
        self._notify_snapshot(snapshot)

    def send(self, data: bytes) -> None:
        """提交一次完整写入。"""
        with self._lock:
            self._require_connected("send")
            worker = self._require_worker()
        worker.send(data)

    def set_line_state(self, *, dtr: bool, rts: bool) -> None:
        """修改已连接会话的 DTR/RTS 状态。"""
        with self._lock:
            self._require_connected("set_line_state")
            worker = self._require_worker()
        worker.set_line_state(dtr=dtr, rts=rts)

    def clear_buffer(self) -> int:
        """清空当前内存缓冲但不重置累计统计。"""
        with self._lock:
            removed = self._buffer.clear()
            snapshot = self._build_snapshot()
        self._notify_snapshot(snapshot)
        return removed

    def on_opened(self, config: SerialConfig) -> None:
        """处理串口打开成功事件。"""
        with self._lock:
            if self._state_machine.state is SessionState.CONNECTING:
                self._state_machine.mark_connected()
            self._start_log_locked()
            record = self._system_record("串口已连接。")
            self._append_record_locked(record)
            snapshot = self._build_snapshot()
        self._notify_record(record)
        self._notify_snapshot(snapshot)

    def on_open_failed(self, error: DomainError) -> None:
        """处理串口打开失败事件。"""
        with self._lock:
            if self._state_machine.state is SessionState.CONNECTING:
                self._state_machine.mark_connect_failed()
            self._last_error = error.to_user_facing()
            record = self._system_record(error.message)
            self._append_record_locked(record)
            snapshot = self._build_snapshot()
        self._notify_record(record)
        self._notify_snapshot(snapshot)

    def on_bytes_received(self, data: bytes) -> None:
        """处理接收数据。"""
        with self._lock:
            if self._state_machine.state is not SessionState.CONNECTED:
                return
            record = LogRecord.from_bytes(
                timestamp_utc=self._clock.now_utc(),
                direction="rx",
                raw=data,
                encoding=self._config.encoding,
                session_id=self._session_id,
            )
            self._append_record_locked(record)
            self._rx_bytes += len(data)
            snapshot = self._build_snapshot()
        self._notify_record(record)
        self._notify_snapshot(snapshot)

    def on_bytes_sent(self, data: bytes) -> None:
        """处理发送完成数据。"""
        with self._lock:
            record = LogRecord.from_bytes(
                timestamp_utc=self._clock.now_utc(),
                direction="tx",
                raw=data,
                encoding=self._config.encoding,
                session_id=self._session_id,
            )
            self._append_record_locked(record)
            self._tx_bytes += len(data)
            snapshot = self._build_snapshot()
        self._notify_record(record)
        self._notify_snapshot(snapshot)

    def on_io_error(self, error: DomainError) -> None:
        """记录 I/O 错误并启动安全断开。"""
        with self._lock:
            if self._last_error is None:
                self._last_error = error.to_user_facing()
            if self._state_machine.state is SessionState.CONNECTED:
                self._state_machine.begin_disconnect()
            record = self._system_record(error.message)
            self._append_record_locked(record)
            snapshot = self._build_snapshot()
        self._notify_record(record)
        self._notify_snapshot(snapshot)

    def on_stopped(self) -> None:
        """处理 Worker 已结束事件。"""
        with self._lock:
            state = self._state_machine.state
            if state is SessionState.CONNECTING:
                self._state_machine.mark_connect_failed()
                if self._last_error is None:
                    self._last_error = TransportIOError(
                        "串口线程在连接完成前结束。"
                    ).to_user_facing()
            elif state is SessionState.CONNECTED:
                self._state_machine.begin_disconnect()
                self._state_machine.mark_disconnected()
            elif state is SessionState.DISCONNECTING:
                self._state_machine.mark_disconnected()
            self._close_log_locked()
            self._worker = None
            snapshot = self._build_snapshot()
        self._notify_snapshot(snapshot)

    def _append_record_locked(self, record: LogRecord) -> None:
        """同时写入内存缓冲和当前自动日志。"""
        self._buffer.append(record)
        service = self._log_service
        if service is None or not service.is_active:
            return
        try:
            service.write(record)
        except DomainError as exc:
            if self._last_error is None:
                self._last_error = exc.to_user_facing()

    def _start_log_locked(self) -> None:
        """按当前偏好启动本次连接的自动日志。"""
        service = self._log_service
        if service is None or not self._auto_log_enabled:
            return
        try:
            service.start(
                directory=self._auto_log_directory,
                port=self._config.port,
                log_format=self._auto_log_format,
            )
        except DomainError as exc:
            if self._last_error is None:
                self._last_error = exc.to_user_facing()

    def _close_log_locked(self) -> None:
        """安全关闭当前自动日志。"""
        service = self._log_service
        if service is None:
            return
        try:
            service.close()
        except DomainError as exc:
            if self._last_error is None:
                self._last_error = exc.to_user_facing()

    def _require_connected(self, action: str) -> None:
        if self._state_machine.state is not SessionState.CONNECTED:
            raise InvalidStateTransitionError(
                self._state_machine.state,
                action,
                SessionState.CONNECTED,
            )

    def _require_worker(self) -> SerialWorker:
        worker = self._worker
        if worker is None or not worker.is_alive:
            raise TransportIOError("串口工作线程未运行。")
        return worker

    def _build_snapshot(self) -> SessionSnapshot:
        return SessionSnapshot(
            session_id=self._session_id,
            title=self._title,
            state=self._state_machine.state,
            config=self._config,
            last_error=self._last_error,
            rx_bytes=self._rx_bytes,
            tx_bytes=self._tx_bytes,
            dropped_records=self._buffer.dropped_records,
        )

    def _system_record(self, message: str) -> LogRecord:
        raw = message.encode("utf-8")
        return LogRecord.from_bytes(
            timestamp_utc=self._clock.now_utc(),
            direction="system",
            raw=raw,
            encoding="utf-8",
            session_id=self._session_id,
        )

    def _notify_current_snapshot(self) -> None:
        with self._lock:
            snapshot = self._build_snapshot()
        self._notify_snapshot(snapshot)

    def _notify_record(self, record: LogRecord) -> None:
        if self._on_record is not None:
            self._on_record(record)

    def _notify_snapshot(self, snapshot: SessionSnapshot) -> None:
        if self._on_snapshot is not None:
            self._on_snapshot(snapshot)
