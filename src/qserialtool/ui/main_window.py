"""QSerialTool 主窗口。"""

from collections.abc import Callable

from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import QMainWindow, QMessageBox, QTabWidget, QToolBar, QWidget

from qserialtool import __version__
from qserialtool.application import SessionManager
from qserialtool.domain import SerialConfig, SessionState
from qserialtool.ui.qt_bridge import QtSessionBridge
from qserialtool.ui.session_tab import SessionTab


class MainWindow(QMainWindow):
    """管理多标签会话的顶层窗口。"""

    def __init__(
        self,
        *,
        session_manager: SessionManager,
        port_provider: Callable[[], tuple[str, ...]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session_manager = session_manager
        self._port_provider = port_provider
        self._session_counter = 0
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.setCentralWidget(self.tabs)
        self.setWindowTitle(f"QSerialTool {__version__}")
        self.resize(1000, 720)
        self._build_actions()
        self.new_session()

    def _build_actions(self) -> None:
        new_action = QAction("新建会话", self)
        new_action.setShortcut("Ctrl+T")
        new_action.triggered.connect(self.new_session)
        close_action = QAction("关闭当前会话", self)
        close_action.setShortcut("Ctrl+W")
        close_action.triggered.connect(lambda: self._close_tab(self.tabs.currentIndex()))
        exit_action = QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)

        file_menu = self.menuBar().addMenu("文件")
        file_menu.addAction(new_action)
        file_menu.addAction(close_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)
        toolbar = QToolBar("主工具栏", self)
        toolbar.addAction(new_action)
        self.addToolBar(toolbar)

    def new_session(self) -> SessionTab:
        """创建并激活新的断开状态会话。"""
        self._session_counter += 1
        bridge = QtSessionBridge()
        controller = self._session_manager.create_session(
            config=SerialConfig(port=""),
            title=f"会话 {self._session_counter}",
            on_snapshot=bridge.publish_snapshot,
            on_record=bridge.publish_record,
        )
        tab = SessionTab(
            controller=controller,
            bridge=bridge,
            port_provider=self._port_provider,
        )
        index = self.tabs.addTab(tab, controller.title)
        self.tabs.setCurrentIndex(index)
        return tab

    def _close_tab(self, index: int) -> None:
        if index < 0:
            return
        widget = self.tabs.widget(index)
        if not isinstance(widget, SessionTab):
            return
        if not widget.request_close():
            return
        self._session_manager.remove_session(widget.controller.session_id)
        self.tabs.removeTab(index)

    def closeEvent(self, event: QCloseEvent) -> None:
        """关闭窗口前确认所有活动会话。"""
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if isinstance(widget, SessionTab) and widget.controller.state in {
                SessionState.CONNECTED,
                SessionState.CONNECTING,
                SessionState.DISCONNECTING,
            }:
                answer = QMessageBox.question(
                    self,
                    "退出 QSerialTool",
                    "仍有活动串口会话，确定全部关闭并退出吗？",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
                break
        self._session_manager.close_all(force=True)
        event.accept()
