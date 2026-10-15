"""应用级诊断日志与未捕获异常钩子。"""

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

from PySide6.QtCore import QtMsgType, qInstallMessageHandler

from qserialtool.infrastructure import default_data_directory

LOGGER_NAME = "qserialtool"
LOG_FILE_NAME = "app.log"
MAX_LOG_BYTES = 1_000_000
LOG_BACKUP_COUNT = 3

_MANAGED_FLAG = "_qserialtool_managed"
_QT_LEVELS = {
    QtMsgType.QtDebugMsg: logging.DEBUG,
    QtMsgType.QtInfoMsg: logging.INFO,
    QtMsgType.QtWarningMsg: logging.WARNING,
    QtMsgType.QtCriticalMsg: logging.ERROR,
    QtMsgType.QtFatalMsg: logging.CRITICAL,
}


def default_diagnostics_path() -> Path:
    """返回当前平台的诊断日志路径。"""
    return default_data_directory() / "logs" / LOG_FILE_NAME


def configure_logging(path: Path | None = None) -> Path:
    """幂等地挂载滚动文件日志，返回实际写入的日志路径。"""
    target = Path(path) if path is not None else default_diagnostics_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if not _has_managed_handler(root, target):
        handler = RotatingFileHandler(
            target,
            maxBytes=MAX_LOG_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        setattr(handler, _MANAGED_FLAG, True)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s")
        )
        root.addHandler(handler)
    if root.getEffectiveLevel() > logging.INFO:
        root.setLevel(logging.INFO)
    return target


def _has_managed_handler(root: logging.Logger, target: Path) -> bool:
    """判断目标路径是否已经有本模块挂载的处理器。"""
    for handler in root.handlers:
        if not getattr(handler, _MANAGED_FLAG, False):
            continue
        if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == target:
            return True
    return False


def install_exception_hooks() -> None:
    """把主线程和子线程的未捕获异常写入诊断日志。"""
    sys.excepthook = _log_unhandled_exception
    threading.excepthook = _log_thread_exception


def _log_unhandled_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType | None,
) -> None:
    logging.getLogger(f"{LOGGER_NAME}.unhandled").critical(
        "主线程未捕获异常。",
        exc_info=(exc_type, exc_value, exc_traceback),
    )


def _log_thread_exception(args: threading.ExceptHookArgs) -> None:
    thread_name = args.thread.name if args.thread is not None else "unknown"
    logging.getLogger(f"{LOGGER_NAME}.unhandled").critical(
        "线程 %s 未捕获异常。",
        thread_name,
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def install_qt_message_handler() -> None:
    """把 Qt 内部消息按级别转发到诊断日志。"""
    qInstallMessageHandler(_handle_qt_message)


def _handle_qt_message(mode: QtMsgType, _context: object, message: str) -> None:
    level = _QT_LEVELS.get(mode, logging.WARNING)
    logging.getLogger(f"{LOGGER_NAME}.qt").log(level, "%s", message)
