"""单会话自动日志的偏好、启动与关闭协调。"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from qserialtool.application.log_service import LogService
from qserialtool.application.session_errors import SessionErrorTracker
from qserialtool.domain import (
    Clock,
    DomainError,
    InvalidStateTransitionError,
    LogFormat,
    LogIOError,
    LogRecord,
    LogSink,
    SessionState,
    ValidationError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LogPreferences:
    """自动日志的初始偏好。"""

    enabled: bool = False
    log_format: LogFormat = "csv"
    directory: str = ""


def validate_log_preferences(
    *,
    state: SessionState,
    enabled: bool,
    log_format: LogFormat,
    directory: str,
) -> None:
    """校验自动日志偏好；非法时抛出领域错误。"""
    if type(enabled) is not bool:
        raise ValidationError("自动日志开关必须是布尔值。")
    if state in {SessionState.CONNECTING, SessionState.CONNECTED, SessionState.DISCONNECTING}:
        raise InvalidStateTransitionError(state, "update_log_preferences")
    if log_format not in {"csv", "txt"}:
        raise ValidationError("自动日志格式必须是 csv 或 txt。")
    if not isinstance(directory, str):
        raise ValidationError("自动日志开关必须是布尔值。")


class SessionLogCoordinator:
    """维护自动日志偏好与 LogService 生命周期，错误经回调上抛。

    启动、写入与关闭都由持有会话锁的调用方调用，自身不加锁；偏好合法性
    （开关类型、会话状态、格式与目录）由调用方在更新时校验。
    """

    def __init__(
        self,
        *,
        sink_factory: Callable[[LogFormat], LogSink] | None,
        clock: Clock,
        preferences: LogPreferences,
        errors: SessionErrorTracker,
    ) -> None:
        self._sink_factory = sink_factory
        self._errors = errors
        self._service = (
            LogService(sink_factory=sink_factory, clock=clock) if sink_factory is not None else None
        )
        self._enabled = preferences.enabled
        self._log_format = preferences.log_format
        self._directory = preferences.directory

    @property
    def enabled(self) -> bool:
        """返回自动日志开关。"""
        return self._enabled

    @property
    def log_format(self) -> LogFormat:
        """返回自动日志格式。"""
        return self._log_format

    @property
    def directory(self) -> str:
        """返回自动日志目录。"""
        return self._directory

    @property
    def path(self) -> Path | None:
        """返回当前连接正在写入的日志路径。"""
        service = self._service
        return service.path if service is not None else None

    def set_preferences(self, *, enabled: bool, log_format: LogFormat, directory: str) -> None:
        """记录下一次连接使用的自动日志设置（合法性由调用方校验）。"""
        self._enabled = enabled
        self._log_format = log_format
        self._directory = directory

    def start(self, port: str) -> None:
        """按当前偏好启动本次连接的自动日志。"""
        service = self._service
        if service is None or not self._enabled:
            return
        try:
            service.start(directory=self._directory, port=port, log_format=self._log_format)
        except DomainError as exc:
            self._errors.record(exc)

    def write(self, record: LogRecord) -> None:
        """把记录写入当前自动日志；失败时输出一次诊断警告。"""
        service = self._service
        if service is None or not service.is_active:
            return
        try:
            service.write(record)
        except DomainError as exc:
            if self._errors.record(exc):
                logger.warning("自动日志写入失败：%s", exc.message)

    def close(self) -> None:
        """安全关闭当前自动日志。"""
        service = self._service
        if service is None:
            return
        try:
            service.close()
        except DomainError as exc:
            self._errors.record(exc)

    def export(self, path: Path, log_format: LogFormat, records: tuple[LogRecord, ...]) -> int:
        """把给定记录导出为 CSV 或 TXT，返回导出条数。"""
        if self._sink_factory is None:
            raise LogIOError("未配置日志输出。")
        if log_format not in {"csv", "txt"}:
            raise ValidationError("日志格式必须是 csv 或 txt。")
        sink = self._sink_factory(log_format)
        try:
            sink.open(path)
            for record in records:
                sink.write(record)
            sink.flush()
        finally:
            sink.close()
        return len(records)
