"""单个串口会话标签页。"""

from collections.abc import Callable

from PySide6.QtCore import QByteArray, Qt, Signal, Slot
from PySide6.QtGui import QHideEvent, QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
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
    SessionPreferences,
    SessionSnapshot,
    SessionState,
)
from qserialtool.ui.connection_panel import ConnectionPanel
from qserialtool.ui.log_panel import LogPanel
from qserialtool.ui.qt_bridge import QtSessionBridge
from qserialtool.ui.receive_panel import ReceivePanel
from qserialtool.ui.send_panel import SendPanel
from qserialtool.ui.theme_manager import data_colors

_STATE_LABELS = {
    SessionState.DISCONNECTED: "未连接",
    SessionState.CONNECTING: "正在连接",
    SessionState.CONNECTED: "已连接",
    SessionState.DISCONNECTING: "正在断开",
    SessionState.ERROR: "错误",
    SessionState.CLOSED: "已关闭",
}


class SessionTab(QWidget):
    """组合左侧连接设置和右侧收发主区域。"""

    preferences_changed = Signal()

    def __init__(
        self,
        *,
        controller: SessionController,
        bridge: QtSessionBridge,
        port_provider: Callable[[], tuple[str, ...]],
        preferences: SessionPreferences | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self._bridge = bridge
        self._snapshot: SessionSnapshot | None = None
        self._last_error_key: tuple[object, str | None] | None = None
        self._sidebar_visible = True
        self._sidebar_width = 300
        self._build_ui(port_provider, preferences)
        bridge.snapshot_changed.connect(self._on_snapshot, Qt.ConnectionType.QueuedConnection)
        bridge.record_received.connect(self._on_record, Qt.ConnectionType.QueuedConnection)
        self._on_snapshot(controller.snapshot)

    def _build_ui(
        self,
        port_provider: Callable[[], tuple[str, ...]],
        preferences: SessionPreferences | None,
    ) -> None:
        self._build_panels(port_provider, preferences)
        self._build_sidebar_toggle()
        self._build_sidebar()
        self._build_content()
        self._build_status_strip()
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.addWidget(self.layout_splitter, 1)
        layout.addWidget(self.status_frame)
        self._connect_panel_signals()

    def _build_panels(
        self,
        port_provider: Callable[[], tuple[str, ...]],
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

    def _build_sidebar(self) -> None:
        self.sidebar_content = QWidget()
        sidebar_layout = QVBoxLayout(self.sidebar_content)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(8)
        sidebar_layout.addWidget(self.connection_panel)
        sidebar_layout.addWidget(self.log_panel)
        sidebar_layout.addStretch(1)

        self.sidebar = QScrollArea()
        self.sidebar.setWidget(self.sidebar_content)
        self.sidebar.setWidgetResizable(True)
        self.sidebar.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar.setMinimumWidth(240)
        self.sidebar.setMaximumWidth(460)
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
        main_layout.setContentsMargins(0, 0, 0, 0)
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
        self.state_indicator = QLabel("●")
        self.status_label = QLabel()
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.status_frame = QFrame()
        self.status_frame.setFrameShape(QFrame.Shape.StyledPanel)
        status_layout = QHBoxLayout(self.status_frame)
        status_layout.setContentsMargins(8, 2, 8, 2)
        status_layout.setSpacing(6)
        status_layout.addWidget(self.state_indicator)
        status_layout.addWidget(self.status_label, 1)

    def _connect_panel_signals(self) -> None:
        self.connection_panel.config_changed.connect(self.preferences_changed.emit)
        self.connection_panel.config_changed.connect(self._refresh_status)
        self.receive_panel.preferences_changed.connect(self.preferences_changed.emit)
        self.send_panel.preferences_changed.connect(self.preferences_changed.emit)
        self.log_panel.preferences_changed.connect(self.preferences_changed.emit)

    def refresh_theme(self) -> None:
        """主题切换后刷新接收区配色和状态点颜色。"""
        self.receive_panel.refresh_theme()
        self._refresh_status()

    def _refresh_status(self) -> None:
        """按最近快照和端口框当前内容刷新状态条。"""
        snapshot = self._snapshot
        if snapshot is None:
            return
        port = snapshot.config.port.strip()
        if not port and snapshot.state in {SessionState.DISCONNECTED, SessionState.ERROR}:
            port = self.connection_panel.port_combo.currentText().strip()
        status_text = (
            f"{_STATE_LABELS[snapshot.state]} | {port or '未选择端口'} | "
            f"RX {snapshot.rx_bytes} B | TX {snapshot.tx_bytes} B"
        )
        self.status_label.setText(status_text)
        self.status_label.setToolTip(status_text)
        self.state_indicator.setStyleSheet(
            f"color: {self._state_color(snapshot.state)}; font-weight: bold;"
        )

    @staticmethod
    def _state_color(state: SessionState) -> str:
        colors = data_colors()
        if state is SessionState.CONNECTED:
            return colors.connected
        if state is SessionState.ERROR:
            return colors.error
        if state in {SessionState.CONNECTING, SessionState.DISCONNECTING}:
            return colors.pending
        return colors.idle

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
        self._sidebar_width = min(max(width, 240), 460)
        self.sidebar_toggle_button.setChecked(not visible)
        self.sidebar_toggle_button.setText("展开设置" if not visible else "收起设置")
        self.sidebar.setVisible(visible)
        if content_splitter_state:
            state = QByteArray.fromBase64(content_splitter_state.encode("ascii"))
            self.receive_send_splitter.restoreState(state)
        if visible:
            self.layout_splitter.setSizes(
                [self._sidebar_width, max(400, self.width() - self._sidebar_width)]
            )
        else:
            self.layout_splitter.setSizes([0, max(400, self.width())])

    def layout_state(self) -> tuple[bool, int, str | None]:
        """返回可持久化的侧栏和主区分隔状态。"""
        if self._sidebar_visible:
            sizes = self.layout_splitter.sizes()
            if sizes:
                self._sidebar_width = min(max(sizes[0], 240), 460)
        splitter_state = bytes(self.receive_send_splitter.saveState().toBase64()).decode("ascii")
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
            auto_log_enabled=self.controller.auto_log_enabled,
            auto_log_format=self.controller.auto_log_format,
            auto_log_directory=self.controller.auto_log_directory,
            send_history=self.send_panel.history,
            send_mode=self.send_panel.mode_combo.currentData(),
            line_ending=self.send_panel.newline_combo.currentData(),
            periodic_interval_ms=self.send_panel.interval_spin.value(),
        )

    @Slot(object)
    def _on_snapshot(self, snapshot: SessionSnapshot) -> None:
        self._snapshot = snapshot
        self.connection_panel.apply_snapshot(snapshot)
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
                self._sidebar_width = min(max(sizes[0], 240), 460)
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
