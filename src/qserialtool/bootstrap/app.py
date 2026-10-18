"""QSerialTool 应用启动和依赖组装。"""

import logging
import sys

from PySide6.QtWidgets import QApplication

from qserialtool import __version__
from qserialtool.application import SessionManager
from qserialtool.bootstrap.diagnostics import (
    configure_logging,
    install_exception_hooks,
    install_qt_message_handler,
)
from qserialtool.domain import AppConfig, LogFormat, LogSink
from qserialtool.infrastructure import (
    CsvLogSink,
    JsonConfigStore,
    SerialPortScanner,
    SerialTransport,
    SystemClock,
    TxtLogSink,
)
from qserialtool.ui.main_window import MainWindow
from qserialtool.ui.window_chrome import keep_window_hidden

DESKTOP_FILE_NAME = "qserialtool"


def create_log_sink(log_format: LogFormat) -> LogSink:
    """按用户选择创建 CSV 或 TXT 日志输出。"""
    if log_format == "csv":
        return CsvLogSink()
    return TxtLogSink()


def configure_desktop_entry(app: QApplication) -> None:
    """声明桌面文件标识，便于 Linux 桌面环境关联 .desktop 图标。"""
    app.setDesktopFileName(DESKTOP_FILE_NAME)


def build_main_window(
    *,
    config_store: JsonConfigStore | None = None,
    initial_config: AppConfig | None = None,
) -> MainWindow:
    """组装主窗口所需的真实实现。"""
    store = config_store or JsonConfigStore()
    config = initial_config if initial_config is not None else store.load()
    manager = SessionManager(
        transport_factory=SerialTransport,
        clock=SystemClock(),
        log_sink_factory=create_log_sink,
    )
    scanner = SerialPortScanner()
    return MainWindow(
        session_manager=manager,
        port_provider=scanner.list_ports,
        config_store=store,
        initial_config=config,
    )


def main() -> int:
    """启动 Qt 应用并返回退出码。"""
    log_path = configure_logging()
    install_exception_hooks()
    install_qt_message_handler()
    logging.getLogger("qserialtool.app").info(
        "QSerialTool %s 启动，诊断日志：%s",
        __version__,
        log_path,
    )
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName("QSerialTool")
    app.setApplicationVersion(__version__)
    configure_desktop_entry(app)
    window = build_main_window()
    # 显示前最后兜底一次：把任何构造期间被系统提前显示的原生窗口重新隐藏，
    # 保证第一个可见帧就是最终形态。
    keep_window_hidden(window)
    window.show()
    return app.exec()
