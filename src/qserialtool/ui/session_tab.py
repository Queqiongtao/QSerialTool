"""单个串口会话标签页。"""

from collections.abc import Callable

from PySide6.QtCore import QByteArray, Qt, Signal, Slot
from PySide6.QtGui import QHideEvent, QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from qserialtool.application import SessionController
from qserialtool.domain import (
    DomainError,
    LogRecord,
    PortInfo,
    SessionPreferences,
    SessionSnapshot,
    SessionState,
    ViewMode,
)
from qserialtool.ui.connection_panel import ConnectionPanel
from qserialtool.ui.font_zoom import FontZoomFilter
from qserialtool.ui.log_panel import LogPanel
from qserialtool.ui.qt_bridge import QtSessionBridge
from qserialtool.ui.receive_panel import ReceivePanel
from qserialtool.ui.send_panel import SendPanel
from qserialtool.ui.status_strip import StatusStrip
from qserialtool.ui.terminal_send_menu import TerminalSendMenu
from qserialtool.ui.view_mode import ViewModeController

# 侧栏宽度约束：默认略窄，避免拖动后留下大片横向空白；下限与领域模型保持一致。
_SIDEBAR_MIN_WIDTH = 260
_SIDEBAR_MAX_WIDTH = 360
_SIDEBAR_DEFAULT_WIDTH = 272

# 右键直接复制后状态条提示的显示时长；期间状态文本保持提示内容。
_COPY_HINT_MS = 1500


class SessionTab(QWidget):
    """组合左侧连接设置和右侧收发主区域。"""

    preferences_changed = Signal()
    title_changed = Signal(str)
    font_zoom_requested = Signal(int)

    def __init__(
        self,
        *,
        controller: SessionController,
        bridge: QtSessionBridge,
        port_provider: Callable[[], tuple[PortInfo, ...]],
        preferences: SessionPreferences | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self._bridge = bridge
        self._snapshot: SessionSnapshot | None = None
        self._title = ""
        self._last_error_key: tuple[object, str | None] | None = None
        self._sidebar_visible = True
        self._sidebar_width = _SIDEBAR_DEFAULT_WIDTH
        self._build_ui(port_provider, preferences)
        bridge.snapshot_changed.connect(self._on_snapshot, Qt.ConnectionType.QueuedConnection)
        bridge.record_received.connect(self._on_record, Qt.ConnectionType.QueuedConnection)
        self._on_snapshot(controller.snapshot)

    def _build_ui(
        self,
        port_provider: Callable[[], tuple[PortInfo, ...]],
        preferences: SessionPreferences | None,
    ) -> None:
        self._build_panels(port_provider, preferences)
        self._font_zoom_filter = FontZoomFilter(self)
        self._font_zoom_filter.zoom_requested.connect(self.font_zoom_requested.emit)
        self.receive_panel.output.viewport().installEventFilter(self._font_zoom_filter)
        self.send_panel.editor.viewport().installEventFilter(self._font_zoom_filter)
        self._build_sidebar_toggle()
        self._build_terminal_send_menu()
        self._build_sidebar()
        self._build_content()
        self._build_view_controller()
        self.set_view_mode(preferences.view_mode if preferences else "split", persist=False)
        self._build_status_strip()
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.addWidget(self.layout_splitter, 1)
        layout.addWidget(self.status_strip.frame)
        self._connect_panel_signals()

    def _build_panels(
        self,
        port_provider: Callable[[], tuple[PortInfo, ...]],
        preferences: SessionPreferences | None,
    ) -> None:
        self.connection_panel = ConnectionPanel(
            controller=self.controller,
            port_provider=port_provider,
        )
        self.receive_panel = ReceivePanel(
            records_provider=lambda: self.controller.records,
            clear_callback=self.controller.clear_buffer,
            preferences=preferences,
        )
        self.send_panel = SendPanel(controller=self.controller, preferences=preferences)
        self.log_panel = LogPanel(controller=self.controller)

    def _build_sidebar_toggle(self) -> None:
        self.sidebar_toggle_button = QToolButton()
        self.sidebar_toggle_button.setText("收起设置")
        self.sidebar_toggle_button.setCheckable(True)
        self.sidebar_toggle_button.setAutoRaise(True)
        self.sidebar_toggle_button.setToolTip("显示或隐藏左侧设置面板")
        self.sidebar_toggle_button.clicked.connect(self._toggle_sidebar)
        self.receive_panel.add_leading_header_widget(self.sidebar_toggle_button)

    def _build_terminal_send_menu(self) -> None:
        self.send_settings_button = TerminalSendMenu()
        self.send_settings_button.send_mode_selected.connect(self.send_panel.set_send_mode)
        self.send_settings_button.line_ending_selected.connect(self.send_panel.set_line_ending)
        self.send_settings_button.history_selected.connect(self.receive_panel.set_terminal_draft)
        self.receive_panel.add_trailing_header_widget(self.send_settings_button)

    def _sync_terminal_send_menu(self) -> None:
        """让终端发送设置菜单反映当前发送偏好和历史。"""
        self.send_settings_button.sync(
            send_mode=self.send_panel.send_mode,
            line_ending=self.send_panel.line_ending,
            history=self.send_panel.history,
        )

    def _build_view_controller(self) -> None:
        self._view_controller = ViewModeController(
            self,
            receive_panel=self.receive_panel,
            send_panel=self.send_panel,
            splitter=self.receive_send_splitter,
            send_settings_button=self.send_settings_button,
        )
        self._view_controller.preferences_changed.connect(self.preferences_changed.emit)
        self.receive_panel.add_trailing_header_widget(self._view_controller.toggle_button)

    @property
    def view_toggle_button(self) -> QToolButton:
        """返回终端/分栏视图切换按钮。"""
        return self._view_controller.toggle_button

    def set_view_mode(self, mode: ViewMode, *, persist: bool = True) -> None:
        """在分栏视图与终端视图之间切换。"""
        self._view_controller.set_mode(mode, persist=persist)

    def _build_sidebar(self) -> None:
        self.sidebar_content = QWidget()
        sidebar_layout = QVBoxLayout(self.sidebar_content)
        # 侧栏面板留白：卡片不贴面板边缘，底部空区由面板底色承接。
        sidebar_layout.setContentsMargins(8, 6, 8, 8)
        sidebar_layout.setSpacing(8)
        sidebar_layout.addWidget(self.connection_panel)
        sidebar_layout.addWidget(self.log_panel)
        # 内容顶部对齐：多余高度留在滚动区背景，避免分组框内部出现大片空白。
        sidebar_layout.addStretch(1)

        self.sidebar = QScrollArea()
        self.sidebar.setObjectName("sessionSidebar")
        self.sidebar.setWidget(self.sidebar_content)
        self.sidebar.setWidgetResizable(True)
        self.sidebar.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar.setMinimumWidth(_SIDEBAR_MIN_WIDTH)
        self.sidebar.setMaximumWidth(_SIDEBAR_MAX_WIDTH)
        self.sidebar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

    def _build_content(self) -> None:
        self.main_content = QWidget()
        receive_send_splitter = QSplitter(Qt.Orientation.Vertical)
        receive_send_splitter.addWidget(self.receive_panel)
        receive_send_splitter.addWidget(self.send_panel)
        receive_send_splitter.setHandleWidth(6)
        receive_send_splitter.setStretchFactor(0, 3)
        receive_send_splitter.setStretchFactor(1, 1)
        self.receive_send_splitter = receive_send_splitter
        main_layout = QVBoxLayout(self.main_content)
        # 与侧栏一致的留白节奏；状态条在根布局中保持通栏贴底。
        main_layout.setContentsMargins(8, 6, 8, 8)
        main_layout.addWidget(receive_send_splitter)

        self.layout_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.layout_splitter.addWidget(self.sidebar)
        self.layout_splitter.addWidget(self.main_content)
        self.layout_splitter.setHandleWidth(6)
        self.layout_splitter.setStretchFactor(0, 0)
        self.layout_splitter.setStretchFactor(1, 1)
        self.layout_splitter.setSizes([self._sidebar_width, 800])
        self.layout_splitter.splitterMoved.connect(self._splitter_moved)

    def _build_status_strip(self) -> None:
        self.status_strip = StatusStrip(self)
        self.status_strip.copy_hint_timer.timeout.connect(self._refresh_status)

    @property
    def status_label(self) -> QLabel:
        """返回状态文本标签。"""
        return self.status_strip.status_label

    @property
    def state_indicator(self) -> QLabel:
        """返回状态点标签。"""
        return self.status_strip.state_indicator

    def _connect_panel_signals(self) -> None:
        self.connection_panel.config_changed.connect(self.preferences_changed.emit)
        self.connection_panel.config_changed.connect(self._refresh_status)
        self.receive_panel.set_line_submit_handler(self.send_panel.send_content)
        self.receive_panel.set_history_provider(lambda: self.send_panel.history)
        self.receive_panel.set_raw_send_handler(self._send_raw_bytes)
        self.receive_panel.output.copied.connect(self._show_copy_hint)
        self.receive_panel.preferences_changed.connect(self.preferences_changed.emit)
        self.send_panel.preferences_changed.connect(self._sync_terminal_send_menu)
        self.send_panel.preferences_changed.connect(self.preferences_changed.emit)
        self.log_panel.preferences_changed.connect(self.preferences_changed.emit)
        self._sync_terminal_send_menu()

    def _send_raw_bytes(self, data: bytes) -> bool:
        """把终端按键序列原样发送给设备。"""
        try:
            self.controller.send(data)
        except DomainError as exc:
            QMessageBox.warning(self, "发送失败", exc.message)
            return False
        return True

    def set_data_font_size(self, size: int) -> None:
        """按全局字号同步接收区与发送编辑框字体。"""
        self.receive_panel.set_data_font_size(size)
        self.send_panel.set_data_font_size(size)

    def refresh_theme(self) -> None:
        """主题切换后刷新接收区配色和状态点颜色。"""
        self.receive_panel.refresh_theme()
        self.status_strip.refresh_theme()
        self._refresh_status()

    def _refresh_status(self) -> None:
        """按最近快照和端口框当前内容刷新状态条。"""
        snapshot = self._snapshot
        if snapshot is None:
            return
        port = snapshot.config.port.strip()
        if not port and snapshot.state in {SessionState.DISCONNECTED, SessionState.ERROR}:
            port = self.connection_panel.current_port()
        port_label = self.connection_panel.describe_port(port) if port else "未选择端口"
        self.status_strip.update(snapshot=snapshot, port_label=port_label)

    @Slot(int)
    def _show_copy_hint(self, count: int) -> None:
        """右键直接复制后，在状态条短暂提示复制的字符数。"""
        self.status_strip.show_copy_hint(count, duration_ms=_COPY_HINT_MS)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.connection_panel.set_refresh_active(True)

    def hideEvent(self, event: QHideEvent) -> None:
        self.connection_panel.set_refresh_active(False)
        super().hideEvent(event)

    def apply_layout_state(
        self,
        *,
        visible: bool,
        width: int,
        content_splitter_state: str | None,
    ) -> None:
        """恢复侧栏宽度、显示状态和接收/发送分隔比例。"""
        self._sidebar_visible = visible
        self._sidebar_width = min(max(width, _SIDEBAR_MIN_WIDTH), _SIDEBAR_MAX_WIDTH)
        self.sidebar_toggle_button.setChecked(not visible)
        self.sidebar_toggle_button.setText("展开设置" if not visible else "收起设置")
        self.sidebar.setVisible(visible)
        if content_splitter_state:
            state = QByteArray.fromBase64(content_splitter_state.encode("ascii"))
            self._view_controller.apply_split_state(state)
        if visible:
            self.layout_splitter.setSizes(
                [self._sidebar_width, max(400, self.width() - self._sidebar_width)]
            )
        else:
            self.layout_splitter.setSizes([0, max(400, self.width())])
        if self._view_controller.mode == "terminal":
            self.set_view_mode("terminal", persist=False)

    def layout_state(self) -> tuple[bool, int, str | None]:
        """返回可持久化的侧栏和主区分隔状态。"""
        if self._sidebar_visible:
            sizes = self.layout_splitter.sizes()
            if sizes:
                self._sidebar_width = min(max(sizes[0], _SIDEBAR_MIN_WIDTH), _SIDEBAR_MAX_WIDTH)
        splitter_state = self._view_controller.split_state_base64()
        return self._sidebar_visible, self._sidebar_width, splitter_state

    def to_preferences(self) -> SessionPreferences:
        """采集当前标签的可持久化偏好。"""
        try:
            config = self.connection_panel.build_config()
        except DomainError:
            config = self.controller.config
        return SessionPreferences(
            title=self.controller.title,
            config=config,
            display_mode=self.receive_panel.display_mode,
            show_timestamp=self.receive_panel.timestamp_check.isChecked(),
            show_rx=self.receive_panel.rx_check.isChecked(),
            show_tx=self.receive_panel.tx_check.isChecked(),
            autoscroll=self.receive_panel.autoscroll_check.isChecked(),
            highlight_enabled=self.receive_panel.highlight_check.isChecked(),
            wrap_enabled=self.receive_panel.wrap_check.isChecked(),
            terminal_timestamp=self.receive_panel.terminal_timestamp_check.isChecked(),
            auto_log_enabled=self.controller.auto_log_enabled,
            auto_log_format=self.controller.auto_log_format,
            auto_log_directory=self.controller.auto_log_directory,
            send_history=self.send_panel.history,
            send_mode=self.send_panel.mode_combo.currentData(),
            line_ending=self.send_panel.newline_combo.currentData(),
            periodic_interval_ms=self.send_panel.interval_spin.value(),
            view_mode=self._view_controller.mode,
        )

    @Slot(object)
    def _on_snapshot(self, snapshot: SessionSnapshot) -> None:
        previous = self._snapshot
        self._snapshot = snapshot
        if snapshot.title != self._title:
            self._title = snapshot.title
            self.title_changed.emit(snapshot.title)
        # 工作线程按记录广播快照；状态与配置未变时跳过重量级面板，只刷新状态条。
        if (
            previous is None
            or snapshot.state is not previous.state
            or snapshot.config != previous.config
        ):
            self.connection_panel.apply_snapshot(snapshot)
        if previous is None or snapshot.state is not previous.state:
            self.send_panel.set_connected(snapshot.state is SessionState.CONNECTED)
            self.log_panel.apply_snapshot(snapshot)
        self._refresh_status()
        if snapshot.last_error is None:
            self._last_error_key = None
        else:
            error_key = (snapshot.last_error.code, snapshot.last_error.diagnostic_id)
            if error_key != self._last_error_key:
                self._last_error_key = error_key
                QMessageBox.warning(self, "串口错误", snapshot.last_error.message)

    @Slot(object)
    def _on_record(self, record: LogRecord) -> None:
        self.receive_panel.append_record(record)

    def _toggle_sidebar(self, hidden: bool) -> None:
        self._sidebar_visible = not hidden
        self.sidebar.setVisible(not hidden)
        self.sidebar_toggle_button.setText("展开设置" if hidden else "收起设置")
        if hidden:
            self.layout_splitter.setSizes([0, max(400, self.width())])
        else:
            self.layout_splitter.setSizes(
                [self._sidebar_width, max(400, self.width() - self._sidebar_width)]
            )
        self.preferences_changed.emit()

    def _splitter_moved(self) -> None:
        if self._sidebar_visible:
            sizes = self.layout_splitter.sizes()
            if sizes:
                self._sidebar_width = min(max(sizes[0], _SIDEBAR_MIN_WIDTH), _SIDEBAR_MAX_WIDTH)
        self.preferences_changed.emit()

    def request_close(self) -> bool:
        """在需要时确认并关闭会话。"""
        state = self.controller.state
        if state in {SessionState.CONNECTED, SessionState.CONNECTING, SessionState.DISCONNECTING}:
            answer = QMessageBox.question(
                self,
                "关闭会话",
                "当前会话仍处于活动状态，确定关闭并释放串口吗？",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False
            self.controller.close(force=True)
        else:
            self.controller.close()
        return True
