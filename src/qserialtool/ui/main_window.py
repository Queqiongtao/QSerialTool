"""QSerialTool 主窗口。"""

import logging
from collections.abc import Callable

from PySide6.QtCore import QByteArray, QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QContextMenuEvent, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QTabWidget,
    QWidget,
)

from qserialtool import __version__
from qserialtool.application import MAX_SESSION_TITLE_LENGTH, SessionManager
from qserialtool.domain import (
    AppConfig,
    ConfigIOError,
    ConfigStore,
    DomainError,
    PortInfo,
    SerialConfig,
    SessionPreferences,
    SessionState,
    Theme,
)
from qserialtool.ui.about_dialog import AboutDialog
from qserialtool.ui.app_icon import app_icon
from qserialtool.ui.help_window import HelpWindow
from qserialtool.ui.main_actions import (
    MainActionCallbacks,
    apply_data_font_size,
    build_main_actions,
    next_font_size,
    refresh_session_tabs,
    show_and_raise,
)
from qserialtool.ui.qt_bridge import QtSessionBridge
from qserialtool.ui.session_tab import _SIDEBAR_DEFAULT_WIDTH, SessionTab
from qserialtool.ui.theme_manager import apply_theme

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """管理多标签会话的顶层窗口。"""

    def __init__(
        self,
        *,
        session_manager: SessionManager,
        port_provider: Callable[[], tuple[PortInfo, ...]],
        config_store: ConfigStore | None = None,
        initial_config: AppConfig | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session_manager = session_manager
        self._port_provider = port_provider
        self._config_store = config_store
        self._last_saved: AppConfig | None = None
        self._session_counter = 0
        self._theme: Theme = initial_config.theme if initial_config is not None else "system"
        self._data_font_size = initial_config.data_font_size if initial_config is not None else 0
        self._sidebar_visible = initial_config.sidebar_visible if initial_config else True
        self._sidebar_width = (
            initial_config.sidebar_width if initial_config else _SIDEBAR_DEFAULT_WIDTH
        )
        self._content_splitter_state = (
            initial_config.content_splitter_state if initial_config else None
        )
        self._help_window: HelpWindow | None = None
        self._about_dialog: AboutDialog | None = None
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
        self.setWindowIcon(app_icon())
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)
        self._build_actions()
        self._restore_or_create_sessions(initial_config)

    def _build_actions(self) -> None:
        actions = build_main_actions(
            self,
            self.tabs,
            theme=self._theme,
            data_font_size=self._data_font_size,
            callbacks=MainActionCallbacks(
                new_session=self._new_session,
                close_current=lambda: self._close_tab(self.tabs.currentIndex()),
                zoom_font=self._zoom_font,
                reset_font_size=self._reset_font_size,
                show_help=self._show_help,
                show_about=self._show_about,
                font_size_changed=self._font_size_changed,
                theme_changed=self._theme_changed,
            ),
        )
        self.main_menu = actions.main_menu
        self.menu_button = actions.menu_button
        self.theme_combo = actions.theme_combo
        self.font_combo = actions.font_combo
        self.new_tab_button = actions.new_tab_button
        self.font_menu = actions.font_menu
        self.font_zoom_in_action = actions.font_zoom_in_action
        self.font_zoom_out_action = actions.font_zoom_out_action
        self.font_reset_action = actions.font_reset_action
        self.help_action = actions.help_action
        self.about_action = actions.about_action
        self._header_tools = actions.header_tools

    def _show_help(self) -> None:
        """打开或前置使用帮助窗口。"""
        self._help_window = show_and_raise(self._help_window, lambda: HelpWindow(self))

    def _show_about(self) -> None:
        """打开或前置关于对话框。"""
        self._about_dialog = show_and_raise(self._about_dialog, lambda: AboutDialog(self))

    def _new_session(self, _checked: bool = False) -> None:
        """标签栏“+”与“☰”菜单的零参数入口；信号附带的布尔状态在此吞掉。"""
        self.new_session()

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
        current_tab = self.tabs.currentWidget()
        if isinstance(current_tab, SessionTab):
            layout_state = current_tab.layout_state()
        else:
            layout_state = (
                self._sidebar_visible,
                self._sidebar_width,
                self._content_splitter_state,
            )
        tab.apply_layout_state(
            visible=layout_state[0],
            width=layout_state[1],
            content_splitter_state=layout_state[2],
        )
        tab.font_zoom_requested.connect(self._zoom_font)
        tab.preferences_changed.connect(self._schedule_save)
        index = self.tabs.addTab(tab, controller.title)
        self.tabs.setTabToolTip(index, controller.title)
        tab.title_changed.connect(
            lambda title, widget=tab: self._on_tab_title_changed(widget, title)
        )
        self.tabs.setCurrentIndex(index)
        # 全局样式表会在挂载时重新 polish 控件并覆盖之前设置的字体，必须在其后重新应用。
        tab.set_data_font_size(self._data_font_size)
        self._schedule_save()
        return tab

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """在标签栏上处理双击重命名与右键菜单。"""
        bar = self.tabs.tabBar()
        if watched is bar:
            if isinstance(event, QMouseEvent) and event.button() is Qt.MouseButton.LeftButton:
                if event.type() is QEvent.Type.MouseButtonDblClick:
                    index = bar.tabAt(event.position().toPoint())
                    if index >= 0:
                        self._prompt_rename(index)
                        return True
            elif isinstance(event, QContextMenuEvent):
                index = bar.tabAt(event.pos())
                if index >= 0:
                    self.tabs.setCurrentIndex(index)
                    self._show_tab_menu(index, event.globalPos())
                    return True
        return super().eventFilter(watched, event)

    def _show_tab_menu(self, index: int, global_pos: QPoint) -> None:
        """在指定位置弹出标签菜单（独立方法便于测试替换）。"""
        self._build_tab_menu(index).exec(global_pos)

    def _build_tab_menu(self, index: int) -> QMenu:
        """构造标签右键菜单，动作作用于指定标签。"""
        menu = QMenu(self)
        rename_action = menu.addAction("重命名…")
        rename_action.triggered.connect(lambda: self._prompt_rename(index))
        close_action = menu.addAction("关闭当前会话")
        close_action.triggered.connect(lambda: self._close_tab(index))
        menu.addSeparator()
        new_action = menu.addAction("新建会话")
        new_action.triggered.connect(self._new_session)
        return menu

    def _ask_session_title(self, initial: str) -> str | None:
        """弹出名称输入框，取消时返回 None。"""
        dialog = QInputDialog(self)
        dialog.setWindowTitle("重命名会话")
        dialog.setLabelText("名称")
        dialog.setInputMode(QInputDialog.InputMode.TextInput)
        dialog.setTextValue(initial)
        # QInputDialog.lineEdit() 在 PySide6 未暴露，改用 findChild 取内部输入框。
        editor = dialog.findChild(QLineEdit)
        if editor is not None:
            editor.setMaxLength(MAX_SESSION_TITLE_LENGTH)
            editor.selectAll()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.textValue()

    def _prompt_rename(self, index: int) -> None:
        """对指定标签发起重命名，失败时提示校验信息。"""
        widget = self.tabs.widget(index)
        if not isinstance(widget, SessionTab):
            return
        title = self._ask_session_title(widget.controller.title)
        if title is None or not title.strip():
            return
        try:
            widget.controller.rename(title)
        except DomainError as exc:
            QMessageBox.warning(self, "重命名失败", exc.message)

    def _on_tab_title_changed(self, tab: SessionTab, title: str) -> None:
        """快照标题变化后刷新标签文本、tooltip 并触发保存。"""
        index = self.tabs.indexOf(tab)
        if index < 0:
            return
        self.tabs.setTabText(index, title)
        self.tabs.setTabToolTip(index, title)
        self._schedule_save()

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
        # removeTab 只把控件移出标签栏，它仍挂在 QTabWidget 下；显式排队销毁，
        # 释放整棵控件树、端口轮询定时器和该会话最多 32 MiB 的记录缓冲。
        widget.deleteLater()
        self._schedule_save()

    def _theme_changed(self) -> None:
        selected = self.theme_combo.currentData()
        if selected not in {"system", "light", "dark"}:
            return
        self._theme = selected
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self._theme)
        refresh_session_tabs(self.tabs, self._data_font_size)
        self._schedule_save()

    def _font_size_changed(self) -> None:
        size = self.font_combo.currentData()
        if not isinstance(size, int):
            return
        self._data_font_size = size
        apply_data_font_size(self.tabs, size)
        self._schedule_save()

    def _zoom_font(self, step: int) -> None:
        """按预设档位放大或缩小全局字号，到达边界后保持不变。"""
        target = next_font_size(self.font_combo.currentData(), step)
        index = self.font_combo.findData(target)
        if index >= 0:
            self.font_combo.setCurrentIndex(index)

    def _reset_font_size(self) -> None:
        """恢复为跟随系统的默认字号。"""
        index = self.font_combo.findData(0)
        if index >= 0:
            self.font_combo.setCurrentIndex(index)

    def _schedule_save(self) -> None:
        if self._config_store is not None:
            self._save_timer.start()

    def _save_config(self) -> None:
        if self._config_store is None:
            return
        active_tab = self.tabs.currentWidget()
        if isinstance(active_tab, SessionTab):
            self._sidebar_visible, self._sidebar_width, self._content_splitter_state = (
                active_tab.layout_state()
            )
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
            sidebar_visible=self._sidebar_visible,
            sidebar_width=self._sidebar_width,
            content_splitter_state=self._content_splitter_state,
            data_font_size=self._data_font_size,
        )
        if config == self._last_saved:
            return
        try:
            self._config_store.save(config)
            self._last_saved = config
        except ConfigIOError as exc:
            logger.warning("配置保存失败：%s", exc.message)
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
