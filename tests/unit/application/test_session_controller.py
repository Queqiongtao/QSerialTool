"""测试单会话控制器的连接生命周期、状态转换与标题校验。"""

from threading import Event
from typing import cast

import pytest
from tests.fixtures.fakes import (
    FakeClock,
    FakeTransport,
    SnapshotRecorder,
    build_controller,
)

from qserialtool.application import (
    MAX_SESSION_TITLE_LENGTH,
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


def test_controller_reports_open_failure_without_losing_config() -> None:
    transport = FakeTransport(open_error=PortBusyError("端口已被占用。"))
    snapshots = SnapshotRecorder()
    controller = build_controller(transport, snapshots=snapshots)

    controller.connect()

    assert snapshots.wait_for(lambda snapshot: snapshot.state is SessionState.ERROR)
    snapshot = controller.snapshot
    assert snapshot.last_error is not None
    assert snapshot.last_error.code is ErrorCode.PORT_BUSY
    assert snapshot.config.port == "COM1"


def test_controller_reports_fatal_io_error_as_disconnected_snapshot() -> None:
    transport = FakeTransport(read_error=TransportIOError("设备断开。"))
    snapshots = SnapshotRecorder()
    controller = build_controller(transport, snapshots=snapshots)
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
    controller = build_controller(FakeTransport(), config=empty_config)

    with pytest.raises(ValidationError):
        controller.connect()
    with pytest.raises(InvalidStateTransitionError):
        controller.send(b"data")
    with pytest.raises(ValidationError):
        controller.disconnect(timeout=0)


def test_controller_requires_force_to_close_active_session() -> None:
    transport = FakeTransport()
    snapshots = SnapshotRecorder()
    controller = build_controller(transport, snapshots=snapshots)
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
    controller = build_controller(transport, snapshots=snapshots)
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
    controller = build_controller(transport, snapshots=snapshots)
    assert controller.title == "测试会话"

    controller.connect()
    assert snapshots.wait_for(lambda snapshot: snapshot.state is SessionState.CONNECTED)
    with pytest.raises(InvalidStateTransitionError):
        controller.connect()
    assert controller.disconnect()


def test_disconnect_is_idempotent_and_rejects_connecting_state() -> None:
    idle = build_controller(FakeTransport())
    assert idle.disconnect()

    transport = BlockingOpenTransport()
    controller = build_controller(transport)
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
    controller = build_controller(FakeTransport())
    config = SerialConfig(port="COM1")

    controller.on_opened(config)
    controller.on_open_failed(PortBusyError())
    controller.on_bytes_received(b"ignored")
    controller.on_io_error(TransportIOError("first"))
    controller.on_io_error(PortBusyError("second"))
    controller.on_stopped()

    assert controller.state is SessionState.DISCONNECTED
    assert controller.records[-1].text == "second"


def test_controller_force_close_without_worker_rejects_commands() -> None:
    controller = build_controller(FakeTransport())
    controller.close()
    assert controller.state is SessionState.CLOSED
    with pytest.raises(InvalidStateTransitionError):
        controller._worker_for("send")


def test_controller_worker_gate_reports_missing_worker_when_connected() -> None:
    # 制造“线程已不在但 on_stopped 尚未清理”的窗口，验证防御分支。
    controller = build_controller(FakeTransport())
    controller._state_machine.connect()
    controller._state_machine.mark_connected()

    with pytest.raises(TransportIOError):
        controller._worker_for("send")


def test_controller_rename_trims_title_and_broadcasts_snapshot() -> None:
    snapshots = SnapshotRecorder()
    controller = build_controller(FakeTransport(), snapshots=snapshots)

    controller.rename("  水泵  ")

    assert controller.title == "水泵"
    assert snapshots.wait_for(lambda snapshot: snapshot.title == "水泵")


def test_controller_rename_rejects_empty_and_too_long_titles() -> None:
    controller = build_controller(FakeTransport())

    with pytest.raises(ValidationError, match="会话名称不能为空"):
        controller.rename("   ")
    with pytest.raises(ValidationError, match="不能超过"):
        controller.rename("x" * (MAX_SESSION_TITLE_LENGTH + 1))

    assert controller.title == "测试会话"


def test_controller_rename_to_same_title_does_not_broadcast() -> None:
    snapshots = SnapshotRecorder()
    controller = build_controller(FakeTransport(), snapshots=snapshots)
    snapshots.snapshots.clear()

    controller.rename("测试会话")

    assert snapshots.snapshots == []
