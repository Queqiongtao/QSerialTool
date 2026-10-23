"""测试多会话注册和端口占用协调。"""

from threading import Event
from typing import cast
from unittest.mock import Mock

import pytest
from tests.fixtures.fakes import FakeClock, FakeTransport

from qserialtool.application import SessionManager
from qserialtool.domain import PortBusyError, SerialConfig, SessionState, ValidationError


class StateRecorder:
    def __init__(self) -> None:
        self.states = []

    def __call__(self, snapshot: object) -> None:
        self.states.append(snapshot.state)


def test_session_manager_creates_and_removes_sessions() -> None:
    ids = iter(("one", "two"))
    manager = SessionManager(
        transport_factory=FakeTransport,
        clock=FakeClock(),
        session_id_factory=lambda: next(ids),
    )
    first = manager.create_session(config=SerialConfig(port="COM1"), title="One")
    second = manager.create_session(config=SerialConfig(port="COM2"))

    assert manager.sessions == (first, second)
    assert manager.get("one") is first
    manager.remove_session("one")
    assert manager.sessions == (second,)
    with pytest.raises(ValidationError):
        manager.get("missing")


def test_session_manager_rejects_duplicate_session_id() -> None:
    manager = SessionManager(
        transport_factory=FakeTransport,
        clock=FakeClock(),
        session_id_factory=lambda: "same",
    )
    manager.create_session(config=SerialConfig(port="COM1"))
    with pytest.raises(ValidationError):
        manager.create_session(config=SerialConfig(port="COM2"))


def test_session_manager_blocks_duplicate_active_port() -> None:
    transports = iter((FakeTransport(), FakeTransport()))
    ids = iter(("one", "two"))
    connected = Event()

    def on_snapshot(snapshot: object) -> None:
        if snapshot.state is SessionState.CONNECTED:
            connected.set()

    manager = SessionManager(
        transport_factory=lambda: next(transports),
        clock=FakeClock(),
        session_id_factory=lambda: next(ids),
    )
    manager.create_session(
        config=SerialConfig(port="COM1"),
        on_snapshot=on_snapshot,
    )
    manager.connect("one")
    assert connected.wait(1.0)

    second = manager.create_session(config=SerialConfig(port="COM1"))
    with pytest.raises(PortBusyError):
        manager.connect(second.session_id)
    manager.close_all(force=True)


def test_session_manager_close_all_closes_registered_sessions() -> None:
    manager = SessionManager(
        transport_factory=FakeTransport,
        clock=FakeClock(),
        session_id_factory=lambda: "one",
    )
    session = manager.create_session(config=SerialConfig(port="COM1"))

    manager.close_all()

    assert session.state is SessionState.CLOSED
    assert manager.sessions == ()


def test_session_manager_applies_receive_buffer_bytes() -> None:
    manager = SessionManager(
        transport_factory=FakeTransport,
        clock=FakeClock(),
        buffer_max_bytes=16 * 1024 * 1024,
    )
    first = manager.create_session(config=SerialConfig(port="COM1"))
    assert first.receive_buffer_bytes == 16 * 1024 * 1024

    manager.set_receive_buffer_bytes(64 * 1024 * 1024)
    assert first.receive_buffer_bytes == 64 * 1024 * 1024

    second = manager.create_session(config=SerialConfig(port="COM2"))
    assert second.receive_buffer_bytes == 64 * 1024 * 1024
    manager.close_all()


@pytest.mark.parametrize("size", [0, -1, 512 * 1024 * 1024 + 1, 16.0, True])
def test_session_manager_rejects_invalid_receive_buffer_bytes(size: object) -> None:
    manager = SessionManager(transport_factory=FakeTransport, clock=FakeClock())
    with pytest.raises(ValidationError):
        manager.set_receive_buffer_bytes(size)  # type: ignore[arg-type]


def test_session_manager_close_all_requests_stops_before_shared_wait() -> None:
    manager = SessionManager(transport_factory=FakeTransport, clock=FakeClock())
    events: list[object] = []
    first = Mock()
    second = Mock()
    first.session_id = "one"
    second.session_id = "two"
    first.request_stop.side_effect = lambda: events.append("stop-one")
    second.request_stop.side_effect = lambda: events.append("stop-two")
    first.close.side_effect = lambda **kwargs: events.append(("close-one", kwargs))
    second.close.side_effect = lambda **kwargs: events.append(("close-two", kwargs))
    manager._sessions = {"one": first, "two": second}

    manager.close_all(force=True, timeout=0.5)

    assert events[:2] == ["stop-one", "stop-two"]
    assert events[2][0] == "close-two"
    assert events[3][0] == "close-one"
    assert 0 <= events[2][1]["timeout"] <= 0.5
    assert manager.sessions == ()


def test_session_manager_close_all_rejects_negative_timeout() -> None:
    manager = SessionManager(transport_factory=FakeTransport, clock=FakeClock())
    with pytest.raises(ValidationError):
        manager.close_all(timeout=-1)


def test_session_manager_rejects_non_callable_factory() -> None:
    with pytest.raises(ValidationError):
        SessionManager(
            transport_factory=cast(object, None),  # type: ignore[arg-type]
            clock=FakeClock(),
        )


def test_session_manager_allows_same_connected_port_on_distinct_session_config() -> None:
    transports = iter((FakeTransport(), FakeTransport()))
    ids = iter(("one", "two"))
    connected = Event()

    def on_snapshot(snapshot: object) -> None:
        if snapshot.state is SessionState.CONNECTED:
            connected.set()

    manager = SessionManager(
        transport_factory=lambda: next(transports),
        clock=FakeClock(),
        session_id_factory=lambda: next(ids),
    )
    first = manager.create_session(
        config=SerialConfig(port="COM1"),
        on_snapshot=on_snapshot,
    )
    manager.connect(first.session_id)
    assert connected.wait(1.0)

    second = manager.create_session(config=SerialConfig(port="COM2"))
    manager.connect(second.session_id, config=SerialConfig(port="COM3"))
    manager.close_all(force=True)
