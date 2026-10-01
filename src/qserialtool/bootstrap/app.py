"""QSerialTool 应用启动和依赖组装。"""

import sys

from PySide6.QtWidgets import QApplication

from qserialtool import __version__
from qserialtool.application import SessionManager
from qserialtool.infrastructure import SerialPortScanner, SerialTransport, SystemClock
from qserialtool.ui.main_window import MainWindow


def build_main_window() -> MainWindow:
    """组装主窗口所需的真实实现。"""
    manager = SessionManager(
        transport_factory=SerialTransport,
        clock=SystemClock(),
    )
    scanner = SerialPortScanner()
    return MainWindow(
        session_manager=manager,
        port_provider=scanner.list_ports,
    )


def main() -> int:
    """启动 Qt 应用并返回退出码。"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName("QSerialTool")
    app.setApplicationVersion(__version__)
    window = build_main_window()
    window.show()
    return app.exec()
