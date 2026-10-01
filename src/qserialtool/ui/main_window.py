"""QSerialTool 主窗口。"""

from collections.abc import Callable

from PySide6.QtCore import QByteArray, QTimer
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QToolBar,
    QWidget,
)

from qserialtool import __version__
from qserialtool.application import SessionManager
from qserialtool.domain import (
    AppConfig,
    ConfigIOError,
    ConfigStore,
    SerialConfig,
    SessionPreferences,
    SessionState,
    Theme,
)
from qserialtool.ui.qt_bridge import QtSessionBridge
from qserialtool.ui.session_tab import SessionTab
from qserialtool.ui.theme_manager import apply_theme

_THEMES: tuple[tuple[str, Theme], ...] = (
    ("跟随系统", "system"),
    ("浅色", "light"),
    ("深色", "dark"),
)


class MainWindow(QMainWindow):
    """管理多标签会话的顶层窗口。"""

    def __init__(
        self,
        *,
        session_manager: SessionManager,
        port_provider: Callable[[], tuple[str, ...]],
        config_store: ConfigStore | None = None,
        initial_config: AppConfig | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session_manager = session_manager
        self._port_provider = port_provider
        self._config_store = config_store
        self._session_counter = 0
        self._theme: Theme = initial_config.theme if initial_config is not None else "system"
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._save_config)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.setCentralWidget(self.tabs)
        self.setWindowTitle(f"QSerialTool {__version__}")
        self.resize(1000, 720)
        self._build_actions()
        self._restore_or_create_sessions(initial_config)

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
        toolbar.addSeparator()
        toolbar.addWidget(QLabel("主题"))
        self.theme_combo = QComboBox()
        for label, value in _THEMES:
            self.theme_combo.addItem(label, value)
        index = self.theme_combo.findData(self._theme)
        self.theme_combo.setCurrentIndex(index if index >= 0 else 0)
        self.theme_combo.currentIndexChanged.connect(self._theme_changed)
        toolbar.addWidget(self.theme_combo)
        self.addToolBar(toolbar)

    def _restore_or_create_sessions(self, config: AppConfig | None) -> None:
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self._theme)
        if config is None or not config.sessions:
            self.new_session()
            return
        if config.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(config.window_geometry.encode("ascii")))
        if config.window_state:
            self.restoreState(QByteArray.fromBase64(config.window_state.encode("ascii")))
        for preferences in config.sessions:
            self.new_session(preferences)
        self.tabs.setCurrentIndex(config.active_session_index)

    def new_session(self, preferences: SessionPreferences | None = None) -> SessionTab:
        """创建并激活新的断开状态会话。"""
        self._session_counter += 1
        config = preferences.config if preferences is not None else SerialConfig(port="")
        title = preferences.title if preferences is not None else f"会话 {self._session_counter}"
        bridge = QtSessionBridge()
        controller = self._session_manager.create_session(
            config=config,
            title=title,
            on_snapshot=bridge.publish_snapshot,
            on_record=bridge.publish_record,
        )
        if preferences is not None:
            controller.update_log_preferences(
                enabled=preferences.auto_log_enabled,
                log_format=preferences.auto_log_format,
                directory=preferences.auto_log_directory,
            )
        tab = SessionTab(
            controller=controller,
            bridge=bridge,
            port_provider=self._port_provider,
            preferences=preferences,
        )
        tab.preferences_changed.connect(self._schedule_save)
        index = self.tabs.addTab(tab, controller.title)
        self.tabs.setCurrentIndex(index)
        self._schedule_save()
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
        self._schedule_save()

    def _theme_changed(self) -> None:
        selected = self.theme_combo.currentData()
        if selected not in {"system", "light", "dark"}:
            return
        self._theme = selected
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self._theme)
        self._schedule_save()

    def _schedule_save(self) -> None:
        if self._config_store is not None:
            self._save_timer.start()

    def _save_config(self) -> None:
        if self._config_store is None:
            return
        preferences: list[SessionPreferences] = []
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if isinstance(widget, SessionTab):
                preferences.append(widget.to_preferences())
        config = AppConfig(
            schema_version=1,
            theme=self._theme,
            window_geometry=bytes(self.saveGeometry().toBase64()).decode("ascii"),
            window_state=bytes(self.saveState().toBase64()).decode("ascii"),
            active_session_index=max(self.tabs.currentIndex(), 0),
            sessions=tuple(preferences),
        )
        try:
            self._config_store.save(config)
        except ConfigIOError as exc:
            self.statusBar().showMessage(exc.message, 5000)

    def closeEvent(self, event: QCloseEvent) -> None:
        """关闭窗口前确认活动会话并保存配置。"""
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
        self._save_timer.stop()
        self._save_config()
        self._session_manager.close_all(force=True)
        event.accept()
