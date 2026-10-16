"""会话底部状态条：状态点、状态文本与复制提示。"""

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget

from qserialtool.domain import SessionSnapshot, SessionState
from qserialtool.ui.theme_manager import data_colors

_STATE_LABELS = {
    SessionState.DISCONNECTED: "未连接",
    SessionState.CONNECTING: "正在连接",
    SessionState.CONNECTED: "已连接",
    SessionState.DISCONNECTING: "正在断开",
    SessionState.ERROR: "错误",
    SessionState.CLOSED: "已关闭",
}


class StatusStrip(QObject):
    """按快照刷新状态点与状态文本，并管理复制提示的显示时长。

    状态点样式表只在颜色变化时重设，避免每次记录刷新都触发 polish。
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.frame = QFrame(parent)
        self.frame.setObjectName("statusFrame")
        self.frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.state_indicator = QLabel("●", self.frame)
        self.status_label = QLabel(self.frame)
        self.status_label.setObjectName("statusText")
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout = QHBoxLayout(self.frame)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)
        layout.addWidget(self.state_indicator)
        layout.addWidget(self.status_label, 1)
        self._color_cache: str | None = None
        self.copy_hint_timer = QTimer(self)
        self.copy_hint_timer.setSingleShot(True)

    def update(self, *, snapshot: SessionSnapshot, port_label: str) -> None:
        """按新快照刷新状态文本；复制提示期间保留提示文本，颜色只在变化时重设。"""
        text = (
            f"{_STATE_LABELS[snapshot.state]} | {port_label} | "
            f"RX {snapshot.rx_bytes} B | TX {snapshot.tx_bytes} B"
        )
        if not self.copy_hint_timer.isActive():
            self.status_label.setText(text)
        self.status_label.setToolTip(text)
        color = self._color_for(snapshot.state)
        if color != self._color_cache:
            self._color_cache = color
            self.state_indicator.setStyleSheet(f"color: {color}; font-weight: bold;")

    def show_copy_hint(self, count: int, *, duration_ms: int) -> None:
        """右键直接复制后，在状态条短暂提示复制的字符数。"""
        self.status_label.setText(f"已复制 {count} 个字符")
        self.copy_hint_timer.start(duration_ms)

    def refresh_theme(self) -> None:
        """主题切换后丢弃颜色缓存，让下次刷新重设状态点样式。"""
        self._color_cache = None

    @staticmethod
    def _color_for(state: SessionState) -> str:
        colors = data_colors()
        if state is SessionState.CONNECTED:
            return colors.connected
        if state is SessionState.ERROR:
            return colors.error
        if state in {SessionState.CONNECTING, SessionState.DISCONNECTING}:
            return colors.pending
        return colors.idle
