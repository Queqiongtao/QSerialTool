"""单个串口会话标签页。"""

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
    QSplitter,
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

_STATE_LABELS = {
    SessionState.DISCONNECTED: "未连接",
    SessionState.CONNECTING: "正在连接",
    SessionState.CONNECTED: "已连接",
    SessionState.DISCONNECTING: "正在断开",
    SessionState.ERROR: "错误",
    SessionState.CLOSED: "已关闭",
}


class SessionTab(QWidget):
    """组合连接、接收、发送和日志面板。"""

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
        self._last_error_key: tuple[object, str | None] | None = None
        self._build_ui(port_provider, preferences)
        bridge.snapshot_changed.connect(
            self._on_snapshot,
            Qt.ConnectionType.QueuedConnection,
        )
        bridge.record_received.connect(
            self._on_record,
            Qt.ConnectionType.QueuedConnection,
        )
        self._on_snapshot(controller.snapshot)

    def _build_ui(
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
        self.send_panel = SendPanel(
            controller=self.controller,
            preferences=preferences,
        )
        self.log_panel = LogPanel(controller=self.controller)
        self.status_label = QLabel()

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.receive_panel)
        splitter.addWidget(self.send_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.connection_panel)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.log_panel)
        layout.addWidget(self.status_label)

        self.connection_panel.config_changed.connect(self.preferences_changed.emit)
        self.receive_panel.preferences_changed.connect(self.preferences_changed.emit)
        self.send_panel.preferences_changed.connect(self.preferences_changed.emit)
        self.log_panel.preferences_changed.connect(self.preferences_changed.emit)

    def to_preferences(self) -> SessionPreferences:
        """采集当前标签的可持久化偏好。"""
        try:
            config = self.connection_panel.build_config()
        except DomainError:
            config = self.controller.config
        send_mode = self.send_panel.mode_combo.currentData()
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
            send_mode=send_mode,
            line_ending=self.send_panel.newline_combo.currentData(),
            periodic_interval_ms=self.send_panel.interval_spin.value(),
        )

    @Slot(object)
    def _on_snapshot(self, snapshot: SessionSnapshot) -> None:
        self.connection_panel.apply_snapshot(snapshot)
        self.send_panel.set_connected(snapshot.state is SessionState.CONNECTED)
        self.log_panel.apply_snapshot(snapshot)
        self.status_label.setText(
            f"{_STATE_LABELS[snapshot.state]} | {snapshot.config.port or '未选择端口'} | "
            f"RX {snapshot.rx_bytes} B | TX {snapshot.tx_bytes} B"
        )
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
