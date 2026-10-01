"""多标签会话注册和端口占用协调。"""

from collections.abc import Callable
from threading import RLock
from uuid import uuid4

from qserialtool.application.session_controller import (
    RecordCallback,
    SessionController,
    SessionControllerOptions,
    SnapshotCallback,
)
from qserialtool.domain import (
    Clock,
    PortBusyError,
    SerialConfig,
    SessionState,
    Transport,
    ValidationError,
)


class SessionManager:
    """创建、查询和关闭当前进程内的串口会话。"""

    def __init__(
        self,
        *,
        transport_factory: Callable[[], Transport],
        clock: Clock,
        session_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if not callable(transport_factory):
            raise ValidationError("transport_factory 必须可调用。")
        self._lock = RLock()
        self._transport_factory = transport_factory
        self._clock = clock
        self._session_id_factory = session_id_factory or (lambda: uuid4().hex)
        self._sessions: dict[str, SessionController] = {}

    @property
    def sessions(self) -> tuple[SessionController, ...]:
        """返回当前会话的稳定顺序快照。"""
        with self._lock:
            return tuple(self._sessions.values())

    def create_session(
        self,
        *,
        config: SerialConfig,
        title: str | None = None,
        on_snapshot: SnapshotCallback | None = None,
        on_record: RecordCallback | None = None,
    ) -> SessionController:
        """创建并注册一个断开状态的会话。"""
        session_id = self._session_id_factory()
        with self._lock:
            if session_id in self._sessions:
                raise ValidationError(f"会话 ID 已存在：{session_id}。")
            controller = SessionController(
                config=config,
                transport_factory=self._transport_factory,
                clock=self._clock,
                options=SessionControllerOptions(
                    session_id=session_id,
                    title=title,
                    on_snapshot=on_snapshot,
                    on_record=on_record,
                ),
            )
            self._sessions[session_id] = controller
            return controller

    def get(self, session_id: str) -> SessionController:
        """按 ID 返回会话。"""
        with self._lock:
            try:
                return self._sessions[session_id]
            except KeyError as exc:
                raise ValidationError(f"找不到会话：{session_id}。") from exc

    def connect(self, session_id: str, config: SerialConfig | None = None) -> None:
        """连接指定会话，并阻止同一进程内重复占用端口。"""
        with self._lock:
            controller = self.get(session_id)
            selected_config = config or controller.config
            selected_config.validate_for_connect()
            normalized_port = selected_config.port.strip().casefold()
            for other in self._sessions.values():
                if other.session_id == session_id:
                    continue
                if other.config.port.strip().casefold() != normalized_port:
                    continue
                if other.state in {
                    SessionState.CONNECTING,
                    SessionState.CONNECTED,
                    SessionState.DISCONNECTING,
                }:
                    raise PortBusyError(f"端口 {selected_config.port} 已被本应用其他会话占用。")
            controller.connect(selected_config)

    def remove_session(self, session_id: str, *, force: bool = False) -> None:
        """关闭并从注册表移除会话。"""
        controller = self.get(session_id)
        controller.close(force=force)
        with self._lock:
            self._sessions.pop(session_id, None)

    def close_all(self, *, force: bool = False) -> None:
        """关闭当前注册的全部会话。"""
        for controller in reversed(self.sessions):
            controller.close(force=force)
        with self._lock:
            self._sessions.clear()
