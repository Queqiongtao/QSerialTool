"""测试会话状态机的合法和非法转换。"""

import pytest

from qserialtool.domain import InvalidStateTransitionError, SessionState, SessionStateMachine


def test_session_state_string_uses_stable_value() -> None:
    assert str(SessionState.CONNECTED) == "connected"


def test_connect_disconnect_cycle_returns_to_disconnected() -> None:
    machine = SessionStateMachine()

    assert machine.connect() is SessionState.CONNECTING
    assert machine.mark_connected() is SessionState.CONNECTED
    assert machine.begin_disconnect() is SessionState.DISCONNECTING
    assert machine.mark_disconnected() is SessionState.DISCONNECTED


def test_connect_failure_can_be_reset_or_retried() -> None:
    machine = SessionStateMachine()
    machine.connect()

    assert machine.mark_connect_failed() is SessionState.ERROR
    assert machine.reset() is SessionState.DISCONNECTED
    assert machine.connect() is SessionState.CONNECTING
    assert machine.mark_connect_failed() is SessionState.ERROR
    assert machine.connect() is SessionState.CONNECTING


def test_cleanup_failure_enters_error_state() -> None:
    machine = SessionStateMachine(SessionState.CONNECTED)
    machine.begin_disconnect()

    assert machine.mark_cleanup_failed() is SessionState.ERROR


@pytest.mark.parametrize(
    ("initial", "action"),
    [
        (SessionState.DISCONNECTED, "mark_connected"),
        (SessionState.DISCONNECTED, "mark_connect_failed"),
        (SessionState.DISCONNECTED, "begin_disconnect"),
        (SessionState.DISCONNECTED, "mark_disconnected"),
        (SessionState.DISCONNECTED, "mark_cleanup_failed"),
        (SessionState.DISCONNECTED, "reset"),
        (SessionState.CONNECTING, "connect"),
        (SessionState.CONNECTING, "mark_disconnected"),
        (SessionState.CONNECTED, "connect"),
        (SessionState.CONNECTED, "mark_connected"),
        (SessionState.DISCONNECTING, "connect"),
        (SessionState.ERROR, "mark_connect_failed"),
        (SessionState.CLOSED, "connect"),
        (SessionState.CLOSED, "reset"),
    ],
)
def test_invalid_transitions_raise_domain_error(initial: SessionState, action: str) -> None:
    machine = SessionStateMachine(initial)
    with pytest.raises(InvalidStateTransitionError):
        getattr(machine, action)()
    assert machine.state is initial


def test_invalid_initial_state_is_rejected() -> None:
    with pytest.raises(InvalidStateTransitionError):
        SessionStateMachine(initial_state="connected")  # type: ignore[arg-type]


def test_close_is_allowed_from_passive_states_and_is_idempotent() -> None:
    for state in (SessionState.DISCONNECTED, SessionState.ERROR):
        machine = SessionStateMachine(state)
        assert machine.close() is SessionState.CLOSED
        assert machine.close() is SessionState.CLOSED


def test_active_states_require_forced_close() -> None:
    for state in (SessionState.CONNECTING, SessionState.CONNECTED, SessionState.DISCONNECTING):
        machine = SessionStateMachine(state)
        with pytest.raises(InvalidStateTransitionError):
            machine.close()
        assert machine.close(force=True) is SessionState.CLOSED


def test_close_rejects_non_boolean_force_value() -> None:
    machine = SessionStateMachine()
    with pytest.raises(InvalidStateTransitionError):
        machine.close(force=1)  # type: ignore[arg-type]
