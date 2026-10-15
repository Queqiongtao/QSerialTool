"""测试诊断日志装配、异常钩子和 Qt 消息转发。"""

import logging
import sys
import threading
from pathlib import Path

import pytest
from PySide6.QtCore import QtMsgType

from qserialtool.bootstrap.diagnostics import (
    _handle_qt_message,
    configure_logging,
    default_diagnostics_path,
    install_exception_hooks,
)
from qserialtool.infrastructure import default_data_directory


def _managed_handlers(target: Path) -> list[logging.Handler]:
    root = logging.getLogger()
    return [
        handler
        for handler in root.handlers
        if getattr(handler, "_qserialtool_managed", False)
        and isinstance(handler, logging.FileHandler)
        and Path(handler.baseFilename) == target
    ]


def _flush_root_handlers() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


def _detach_managed_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_qserialtool_managed", False):
            root.removeHandler(handler)
            handler.close()


@pytest.fixture(autouse=True)
def _restore_logging_state() -> None:
    """还原根记录器级别并移除本模块挂载的处理器。"""
    root = logging.getLogger()
    previous_level = root.level
    yield
    root.setLevel(previous_level)
    _detach_managed_handlers()


def test_default_diagnostics_path_follows_platform_env(monkeypatch: object, tmp_path: Path) -> None:
    if sys.platform.startswith("win"):
        monkeypatch.setenv("APPDATA", str(tmp_path))
    else:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert default_data_directory() == tmp_path / "QSerialTool"
    assert default_diagnostics_path() == tmp_path / "QSerialTool" / "logs" / "app.log"


def test_configure_logging_writes_file_and_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "logs" / "app.log"

    assert configure_logging(target) == target
    assert configure_logging(target) == target
    logging.getLogger("qserialtool.test").warning("诊断消息")
    _flush_root_handlers()

    assert len(_managed_handlers(target)) == 1
    content = target.read_text(encoding="utf-8")
    assert "诊断消息" in content
    assert "WARNING" in content
    assert "[MainThread]" in content
    assert "qserialtool.test" in content


def test_exception_hooks_write_tracebacks(tmp_path: Path) -> None:
    target = configure_logging(tmp_path / "app.log")
    previous_sys_hook = sys.excepthook
    previous_thread_hook = threading.excepthook
    try:
        install_exception_hooks()
        try:
            raise RuntimeError("主线程崩溃")
        except RuntimeError as exc:
            sys.excepthook(type(exc), exc, exc.__traceback__)
        threading.excepthook(
            threading.ExceptHookArgs(
                (ValueError, ValueError("线程崩溃"), None, threading.current_thread())
            )
        )
    finally:
        sys.excepthook = previous_sys_hook
        threading.excepthook = previous_thread_hook

    _flush_root_handlers()
    content = target.read_text(encoding="utf-8")
    assert "主线程未捕获异常" in content
    assert "主线程崩溃" in content
    assert "线程 MainThread 未捕获异常" in content
    assert "线程崩溃" in content


def test_qt_message_handler_maps_levels(caplog: object) -> None:
    with caplog.at_level(logging.INFO, logger="qserialtool.qt"):
        _handle_qt_message(QtMsgType.QtInfoMsg, None, "普通消息")
        _handle_qt_message(QtMsgType.QtWarningMsg, None, "警告消息")
        _handle_qt_message(QtMsgType.QtCriticalMsg, None, "严重消息")

    levels = {record.message: record.levelno for record in caplog.records}
    assert levels["普通消息"] == logging.INFO
    assert levels["警告消息"] == logging.WARNING
    assert levels["严重消息"] == logging.ERROR
