"""会话底部状态条：状态点、状态文本与复制提示。"""

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget

from qserialtool.domain import SerialConfig, SessionSnapshot, SessionState
from qserialtool.ui.theme_manager import data_colors

_STATE_LABELS = {
    SessionState.DISCONNECTED: "未连接",
    SessionState.CONNECTING: "正在连接",
    SessionState.CONNECTED: "已连接",
    SessionState.DISCONNECTING: "正在断开",
    SessionState.ERROR: "错误",
    SessionState.CLOSED: "已关闭",
}

# 流控的短标签；“none”不显示，避免状态条出现无意义后缀。
_FLOW_LABELS = {
    "rtscts": "RTS/CTS",
    "xonxoff": "XON/XOFF",
    "dsrdtr": "DSR/DTR",
}

# 字节数进位基数与单位表：先按 1024 逐级换算，B 档不保留小数。
_BYTE_UNITS = ("KB", "MB", "GB")
_BYTES_PER_UNIT = 1024


def format_serial_params(config: SerialConfig) -> str:
    """把串口配置汇总为 ``115200 8N1`` 形式的速览文本。"""
    stop_text = f"{config.stopbits:g}"
    text = f"{config.baudrate} {config.bytesize}{config.parity}{stop_text}"
    flow = _FLOW_LABELS.get(config.flow_control)
    if flow is not None:
        text = f"{text} {flow}"
    return text


def format_byte_count(count: int) -> str:
    """把字节数换算为易读文本：不足 1 KiB 显示 B，之后逐级使用 KB/MB/GB。"""
    if count < _BYTES_PER_UNIT:
        return f"{count} B"
    value = float(count)
    for unit in _BYTE_UNITS:
        value /= _BYTES_PER_UNIT
        if value < _BYTES_PER_UNIT:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} TB"


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
        parts = [
            _STATE_LABELS[snapshot.state],
            port_label,
        ]
        # 连接参数只有连接成功后才有意义（未连接时显示空端口默认值会误导）。
        if snapshot.state is SessionState.CONNECTED:
            parts.append(format_serial_params(snapshot.config))
        parts.append(f"RX {format_byte_count(snapshot.rx_bytes)}")
        parts.append(f"TX {format_byte_count(snapshot.tx_bytes)}")
        if snapshot.state is SessionState.ERROR and snapshot.last_error is not None:
            parts.append(f"错误：{snapshot.last_error.message}")
        text = " | ".join(parts)
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
