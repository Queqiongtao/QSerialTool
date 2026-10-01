"""不依赖线程实现的串口会话状态机。"""

from .errors import InvalidStateTransitionError
from .states import SessionState


class SessionStateMachine:
    """验证并执行会话状态转换。"""

    def __init__(self, initial_state: SessionState = SessionState.DISCONNECTED) -> None:
        if not isinstance(initial_state, SessionState):
            raise InvalidStateTransitionError(
                initial_state, "initialize", SessionState.DISCONNECTED
            )
        self._state = initial_state

    @property
    def state(self) -> SessionState:
        """返回当前状态。"""
        return self._state

    def _transition(
        self,
        allowed_states: frozenset[SessionState],
        target_state: SessionState,
        action: str,
    ) -> SessionState:
        if self._state not in allowed_states:
            raise InvalidStateTransitionError(self._state, action, target_state)
        self._state = target_state
        return self._state

    def connect(self) -> SessionState:
        """从断开或错误状态开始连接。"""
        return self._transition(
            frozenset({SessionState.DISCONNECTED, SessionState.ERROR}),
            SessionState.CONNECTING,
            "connect",
        )

    def mark_connected(self) -> SessionState:
        """确认串口已经成功打开。"""
        return self._transition(
            frozenset({SessionState.CONNECTING}),
            SessionState.CONNECTED,
            "mark_connected",
        )

    def mark_connect_failed(self) -> SessionState:
        """确认串口打开失败。"""
        return self._transition(
            frozenset({SessionState.CONNECTING}),
            SessionState.ERROR,
            "mark_connect_failed",
        )

    def begin_disconnect(self) -> SessionState:
        """从已连接状态开始清理。"""
        return self._transition(
            frozenset({SessionState.CONNECTED}),
            SessionState.DISCONNECTING,
            "begin_disconnect",
        )

    def mark_disconnected(self) -> SessionState:
        """确认资源已清理并回到断开状态。"""
        return self._transition(
            frozenset({SessionState.DISCONNECTING}),
            SessionState.DISCONNECTED,
            "mark_disconnected",
        )

    def mark_cleanup_failed(self) -> SessionState:
        """记录清理超时或清理失败。"""
        return self._transition(
            frozenset({SessionState.DISCONNECTING}),
            SessionState.ERROR,
            "mark_cleanup_failed",
        )

    def reset(self) -> SessionState:
        """从可恢复错误状态回到断开状态。"""
        return self._transition(
            frozenset({SessionState.ERROR}),
            SessionState.DISCONNECTED,
            "reset",
        )

    def close(self, *, force: bool = False) -> SessionState:
        """关闭状态机；活动状态要求显式强制关闭。"""
        if type(force) is not bool:
            raise InvalidStateTransitionError(self._state, "close")
        if self._state is SessionState.CLOSED:
            return self._state
        if self._state in {SessionState.DISCONNECTED, SessionState.ERROR} or force:
            self._state = SessionState.CLOSED
            return self._state
        raise InvalidStateTransitionError(self._state, "close", SessionState.CLOSED)
