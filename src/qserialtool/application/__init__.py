"""串口会话、日志和配置的应用用例编排。"""

from .log_service import (
    DEFAULT_MAX_FILE_BYTES,
    LogService,
    default_log_directory,
    sanitize_port_name,
)
from .serial_worker import SerialWorker, SerialWorkerOptions, WorkerEventHandler
from .session_controller import SessionController
from .session_manager import SessionManager
from .session_options import (
    MAX_SESSION_TITLE_LENGTH,
    RecordCallback,
    SessionControllerOptions,
    SnapshotCallback,
)

__all__ = [
    "DEFAULT_MAX_FILE_BYTES",
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
