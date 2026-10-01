"""测试单会话控制器状态、缓冲和资源生命周期。"""

from threading import Condition, Event
from typing import cast

import pytest
from tests.fixtures.fakes import FakeClock, FakeTransport

from qserialtool.application import (
    SerialWorkerOptions,
    SessionController,
    SessionControllerOptions,
)
from qserialtool.domain import (
    ErrorCode,
    InvalidStateTransitionError,
    PortBusyError,
    SerialConfig,
    SessionState,
    TransportIOError,
    ValidationError,
)


class SnapshotRecorder:
    """记录快照并支持条件等待。"""

    def __init__(self) -> None:
        self.condition = Condition()
        self.snapshots = []

    def __call__(self, snapshot: object) -> None:
        with self.condition:
            self.snapshots.append(snapshot)
            self.condition.notify_all()

    def wait_for(self, predicate: object, timeout: float = 2.0) -> bool:
        with self.condition:
            return self.condition.wait_for(
                lambda: any(predicate(item) for item in self.snapshots), timeout
            )


class RecordRecorder:
    """记录串口数据事件。"""

    def __init__(self) -> None:
        self.condition = Condition()
        self.records = []

    def __call__(self, record: object) -> None:
        with self.condition:
            self.records.append(record)
            self.condition.notify_all()

    def wait_for(self, predicate: object, timeout: float = 2.0) -> bool:
        with self.condition:
            return self.condition.wait_for(
                lambda: any(predicate(item) for item in self.records), timeout
            )


def _controller(
    transport: FakeTransport,
    *,
    config: SerialConfig | None = None,
    snapshots: SnapshotRecorder | None = None,
    records: RecordRecorder | None = None,
) -> SessionController:
    return SessionController(
        config=config or SerialConfig(port="COM1"),
        transport_factory=lambda: transport,
        clock=FakeClock(),
        options=SessionControllerOptions(
            session_id="session-1",
            title="测试会话",
            on_snapshot=snapshots,
            on_record=records,
        ),
    )


def test_controller_connects_sends_receives_and_disconnects() -> None:
    transport = FakeTransport()
    snapshots = SnapshotRecorder()
    records = RecordRecorder()
    controller = _controller(transport, snapshots=snapshots, records=records)

    assert controller.state is SessionState.DISCONNECTED
    controller.connect()
    assert snapshots.wait_for(lambda snapshot: snapshot.state is SessionState.CONNECTED)

    controller.send(b"tx")
    assert transport.write_event.wait(1.0)
    assert snapshots.wait_for(lambda snapshot: snapshot.tx_bytes == 2)

    transport.push_read(b"rx")
    assert records.wait_for(lambda record: record.direction == "rx" and record.raw == b"rx")
    assert snapshots.wait_for(lambda snapshot: snapshot.rx_bytes == 2)

    assert controller.disconnect()
    assert controller.state is SessionState.DISCONNECTED
    assert transport.close_count == 1


def test_controller_reports_open_failure_without_losing_config() -> None:
    transport = FakeTransport(open_error=PortBusyError("端口已被占用。"))
    snapshots = SnapshotRecorder()
    controller = _controller(transport, snapshots=snapshots)

    controller.connect()

    assert snapshots.wait_for(lambda snapshot: snapshot.state is SessionState.ERROR)
    snapshot = controller.snapshot
    assert snapshot.last_error is not None
    assert snapshot.last_error.code is ErrorCode.PORT_BUSY
    assert snapshot.config.port == "COM1"


def test_controller_reports_fatal_io_error_as_disconnected_snapshot() -> None:
    transport = FakeTransport(read_error=TransportIOError("设备断开。"))
    snapshots = SnapshotRecorder()
    controller = _controller(transport, snapshots=snapshots)
    controller.connect()
    assert snapshots.wait_for(lambda snapshot: snapshot.state is SessionState.CONNECTED)

    assert snapshots.wait_for(
        lambda snapshot: (
            snapshot.state is SessionState.DISCONNECTED and snapshot.last_error is not None
        )
    )
    assert controller.snapshot.last_error is not None


def test_controller_rejects_invalid_operations() -> None:
    empty_config = SerialConfig(port="")
    controller = _controller(FakeTransport(), config=empty_config)

    with pytest.raises(ValidationError):
        controller.connect()
    with pytest.raises(InvalidStateTransitionError):
        controller.send(b"data")
    with pytest.raises(ValidationError):
        controller.disconnect(timeout=0)


def test_controller_clear_buffer_keeps_counters() -> None:
    transport = FakeTransport()
    snapshots = SnapshotRecorder()
    controller = _controller(transport, snapshots=snapshots)
    controller.connect()
    assert snapshots.wait_for(lambda snapshot: snapshot.state is SessionState.CONNECTED)

    removed = controller.clear_buffer()

    assert removed == 1
    assert controller.records == ()
    assert controller.snapshot.rx_bytes == 0
    assert controller.disconnect()


def test_controller_requires_force_to_close_active_session() -> None:
    transport = FakeTransport()
    snapshots = SnapshotRecorder()
    controller = _controller(transport, snapshots=snapshots)
    controller.connect()
    assert snapshots.wait_for(lambda snapshot: snapshot.state is SessionState.CONNECTED)

    with pytest.raises(InvalidStateTransitionError):
        controller.close()
    controller.close(force=True)

    assert controller.state is SessionState.CLOSED
    assert transport.close_count == 1


def test_controller_set_line_state() -> None:
    transport = FakeTransport()
    snapshots = SnapshotRecorder()
    controller = _controller(transport, snapshots=snapshots)
    controller.connect()
    assert snapshots.wait_for(lambda snapshot: snapshot.state is SessionState.CONNECTED)

    controller.set_line_state(dtr=False, rts=True)

    assert transport.line_event.wait(1.0)
    assert transport.line_states[-1] == (False, True)
    assert controller.disconnect()


def test_controller_rejects_blank_session_id() -> None:
    with pytest.raises(ValidationError):
        SessionController(
            config=SerialConfig(port="COM1"),
            transport_factory=FakeTransport,
            clock=FakeClock(),
            options=SessionControllerOptions(session_id="   "),
        )


class BlockingOpenTransport(FakeTransport):
    """在 open 阶段阻塞，用于覆盖连接中的取消边界。"""

    def __init__(self) -> None:
        super().__init__()
        self.open_started = Event()
        self.release_open = Event()

    def open(self, config: SerialConfig) -> None:
        self.open_started.set()
        self.release_open.wait(1.0)
        super().open(config)


def test_controller_rejects_non_callable_transport_factory() -> None:
    with pytest.raises(ValidationError):
        SessionController(
            config=SerialConfig(port="COM1"),
            transport_factory=cast(object, None),  # type: ignore[arg-type]
            clock=FakeClock(),
        )


def test_controller_rejects_blank_title() -> None:
    with pytest.raises(ValidationError):
        SessionController(
            config=SerialConfig(port=""),
            transport_factory=FakeTransport,
            clock=FakeClock(),
            options=SessionControllerOptions(title="   "),
        )


def test_controller_rejects_duplicate_connect_and_exposes_title() -> None:
    transport = FakeTransport()
    snapshots = SnapshotRecorder()
    controller = _controller(transport, snapshots=snapshots)
    assert controller.title == "测试会话"

    controller.connect()
    assert snapshots.wait_for(lambda snapshot: snapshot.state is SessionState.CONNECTED)
    with pytest.raises(InvalidStateTransitionError):
        controller.connect()
    assert controller.disconnect()


def test_disconnect_is_idempotent_and_rejects_connecting_state() -> None:
    idle = _controller(FakeTransport())
    assert idle.disconnect()

    transport = BlockingOpenTransport()
    controller = _controller(transport)
    controller.connect()
    assert transport.open_started.wait(1.0)
    with pytest.raises(InvalidStateTransitionError):
        controller.disconnect()
    transport.release_open.set()
    assert transport.opened_event.wait(1.0)
    controller.close(force=True)


def test_disconnect_timeout_transitions_to_error_without_leaking_thread() -> None:
    transport = FakeTransport()
    snapshots = SnapshotRecorder()
    controller = SessionController(
        config=SerialConfig(port="COM1"),
        transport_factory=lambda: transport,
        clock=FakeClock(),
        options=SessionControllerOptions(
            session_id="timeout-session",
            on_snapshot=snapshots,
            worker_options=SerialWorkerOptions(read_timeout=0.2),
        ),
    )
    controller.connect()
    assert snapshots.wait_for(lambda snapshot: snapshot.state is SessionState.CONNECTED)

    assert not controller.disconnect(timeout=0.001)
    assert snapshots.wait_for(lambda snapshot: snapshot.state is SessionState.ERROR)
    assert transport.closed_event.wait(1.0)


def test_controller_callback_branch_guards() -> None:
    controller = _controller(FakeTransport())
    config = SerialConfig(port="COM1")

    controller.on_opened(config)
    controller.on_open_failed(PortBusyError())
    controller.on_bytes_received(b"ignored")
    controller.on_io_error(TransportIOError("first"))
    controller.on_io_error(PortBusyError("second"))
    controller.on_stopped()

    assert controller.state is SessionState.DISCONNECTED
    assert controller.records[-1].text == "second"


def test_controller_force_close_without_worker_and_missing_worker_error() -> None:
    controller = _controller(FakeTransport())
    controller.close()
    assert controller.state is SessionState.CLOSED
    with pytest.raises(TransportIOError):
        controller._require_worker()
