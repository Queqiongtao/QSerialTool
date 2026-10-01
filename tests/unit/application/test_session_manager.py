"""测试多会话注册和端口占用协调。"""

from threading import Event
from typing import cast

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
