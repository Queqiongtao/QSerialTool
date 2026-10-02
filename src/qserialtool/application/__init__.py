"""串口会话、日志和配置的应用用例编排。"""

from .log_service import LogService, default_log_directory, sanitize_port_name
from .serial_worker import SerialWorker, SerialWorkerOptions, WorkerEventHandler
from .session_controller import (
    MAX_SESSION_TITLE_LENGTH,
    RecordCallback,
    SessionController,
    SessionControllerOptions,
    SnapshotCallback,
)
from .session_manager import SessionManager

__all__ = [
    "MAX_SESSION_TITLE_LENGTH",
    "LogService",
    "RecordCallback",
    "SerialWorker",
    "SerialWorkerOptions",
    "SessionController",
    "SessionControllerOptions",
    "SessionManager",
    "SnapshotCallback",
    "WorkerEventHandler",
    "default_log_directory",
    "sanitize_port_name",
]
