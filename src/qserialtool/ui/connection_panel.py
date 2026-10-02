"""串口连接参数和连接控制面板。"""

from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QStyle,
    QToolButton,
    QWidget,
)

from qserialtool.application import SessionController
from qserialtool.domain import (
    DomainError,
    PortInfo,
    SerialConfig,
    SessionSnapshot,
    SessionState,
    ValidationError,
)

_BAUDRATES = ("9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600")
_PARITIES = (("无", "N"), ("偶校验", "E"), ("奇校验", "O"), ("标记", "M"), ("空格", "S"))
_FLOW_CONTROLS = (
    ("无", "none"),
    ("XON/XOFF", "xonxoff"),
    ("RTS/CTS", "rtscts"),
    ("DSR/DTR", "dsrdtr"),
)

# 自动枚举周期放宽到 30 s，热插拔主要靠端口行右侧的刷新按钮即时感知。
_PORT_REFRESH_INTERVAL_MS = 30_000


class ConnectionPanel(QGroupBox):
    config_changed = Signal()

    """编辑串口参数并管理单个连接。"""

    def __init__(
        self,
        *,
        controller: SessionController,
        port_provider: Callable[[], tuple[PortInfo, ...]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("串口设置", parent)
        self._controller = controller
        self._port_provider = port_provider
        self._updating = False
        self._port_items: tuple[PortInfo, ...] = ()
        self._label_to_device: dict[str, str] = {}
        self._build_ui()
        self._port_timer = QTimer(self)
        self._port_timer.setInterval(_PORT_REFRESH_INTERVAL_MS)
        self._port_timer.timeout.connect(self._refresh_ports)
        self._port_timer.start()
        self._refresh_ports()
        self.apply_snapshot(controller.snapshot)

    def _build_ui(self) -> None:
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(120)
        self.refresh_button = QToolButton()
        self.refresh_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self.refresh_button.setToolTip("刷新端口列表")
        self.refresh_button.setFixedSize(24, 24)
        self.refresh_button.clicked.connect(self._refresh_ports)
        self.baud_combo = QComboBox()
        self.baud_combo.setEditable(True)
        self.baud_combo.addItems(_BAUDRATES)
        self.bytesize_combo = QComboBox()
        for value in (5, 6, 7, 8):
            self.bytesize_combo.addItem(str(value), value)
        self.parity_combo = QComboBox()
        for label, value in _PARITIES:
            self.parity_combo.addItem(label, value)
        self.stopbits_combo = QComboBox()
        for label, value in (("1", 1.0), ("1.5", 1.5), ("2", 2.0)):
            self.stopbits_combo.addItem(label, value)
        self.flow_combo = QComboBox()
        for label, value in _FLOW_CONTROLS:
            self.flow_combo.addItem(label, value)
        self.dtr_check = QCheckBox("DTR")
        self.rts_check = QCheckBox("RTS")
        self.connect_button = QPushButton("连接")
        self.connect_button.clicked.connect(self._toggle_connection)
        self.dtr_check.toggled.connect(self._line_state_changed)
        self.rts_check.toggled.connect(self._line_state_changed)
        self.port_combo.editTextChanged.connect(self._config_changed)
        self.port_combo.currentIndexChanged.connect(self._on_port_index_changed)
        self.baud_combo.currentTextChanged.connect(self._config_changed)
        for combo in (
            self.bytesize_combo,
            self.parity_combo,
            self.stopbits_combo,
            self.flow_combo,
        ):
            combo.currentIndexChanged.connect(self._config_changed)

        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        port_row = QWidget()
        port_row_layout = QHBoxLayout(port_row)
        port_row_layout.setContentsMargins(0, 0, 0, 0)
        port_row_layout.setSpacing(4)
        port_row_layout.addWidget(self.port_combo, 1)
        port_row_layout.addWidget(self.refresh_button)
        layout.addRow("端口", port_row)
        layout.addRow("波特率", self.baud_combo)
        layout.addRow("数据位", self.bytesize_combo)
        layout.addRow("校验位", self.parity_combo)
        layout.addRow("停止位", self.stopbits_combo)
        layout.addRow("流控", self.flow_combo)
        line_layout = QHBoxLayout()
        line_layout.addWidget(self.dtr_check)
        line_layout.addWidget(self.rts_check)
        line_layout.addStretch(1)
        layout.addRow("线路", line_layout)
        layout.addRow(self.connect_button)

    def apply_snapshot(self, snapshot: SessionSnapshot) -> None:
        """根据会话状态更新控件。"""
        self._updating = True
        try:
            with QSignalBlocker(self.dtr_check), QSignalBlocker(self.rts_check):
                self.dtr_check.setChecked(snapshot.config.dtr)
                self.rts_check.setChecked(snapshot.config.rts)
            if snapshot.state in {SessionState.DISCONNECTED, SessionState.ERROR}:
                self.baud_combo.setEditText(str(snapshot.config.baudrate))
                self._select_data(self.bytesize_combo, snapshot.config.bytesize)
                self._select_data(self.parity_combo, snapshot.config.parity)
                self._select_data(self.stopbits_combo, snapshot.config.stopbits)
                self._select_data(self.flow_combo, snapshot.config.flow_control)
                if snapshot.config.port:
                    self.port_combo.setEditText(snapshot.config.port)
            self._set_editable(snapshot.state in {SessionState.DISCONNECTED, SessionState.ERROR})
            self.connect_button.setEnabled(snapshot.state is not SessionState.DISCONNECTING)
            button_labels = {
                SessionState.DISCONNECTED: "连接",
                SessionState.CONNECTING: "正在连接",
                SessionState.CONNECTED: "断开",
                SessionState.DISCONNECTING: "正在断开",
                SessionState.ERROR: "重试",
                SessionState.CLOSED: "已关闭",
            }
            self.connect_button.setText(button_labels[snapshot.state])
            self._update_port_tooltip()
        finally:
            self._updating = False

    def _toggle_connection(self) -> None:
        state = self._controller.state
        try:
            if state is SessionState.CONNECTED:
                self._controller.disconnect()
            elif state in {SessionState.DISCONNECTED, SessionState.ERROR}:
                self._controller.connect(self.build_config())
        except DomainError as exc:
            QMessageBox.warning(self, "串口操作失败", exc.message)

    def build_config(self) -> SerialConfig:
        try:
            baudrate = int(self.baud_combo.currentText().strip())
        except ValueError as exc:
            raise ValidationError("波特率必须是正整数。") from exc
        return SerialConfig(
            port=self.current_port(),
            baudrate=baudrate,
            bytesize=int(self.bytesize_combo.currentData()),
            parity=self.parity_combo.currentData(),
            stopbits=float(self.stopbits_combo.currentData()),
            flow_control=self.flow_combo.currentData(),
            dtr=self.dtr_check.isChecked(),
            rts=self.rts_check.isChecked(),
            encoding=self._controller.config.encoding,
        )

    def _config_changed(self) -> None:
        if not self._updating:
            self.config_changed.emit()

    def _line_state_changed(self) -> None:
        if self._updating:
            return
        self.config_changed.emit()
        if self._controller.state is not SessionState.CONNECTED:
            return
        try:
            self._controller.set_line_state(
                dtr=self.dtr_check.isChecked(),
                rts=self.rts_check.isChecked(),
            )
        except DomainError as exc:
            QMessageBox.warning(self, "线路控制失败", exc.message)

    def current_port(self) -> str:
        """返回当前端口设备名，显示标签会被还原成设备名。"""
        text = self.port_combo.currentText().strip()
        return self._label_to_device.get(text, text)

    def describe_port(self, device: str) -> str:
        """返回带设备描述的端口显示文本，未知设备原样返回。"""
        description = self._description_for(device) if device else ""
        if description:
            return f"{device} ({description})"
        return device

    def _description_for(self, device: str) -> str:
        for info in self._port_items:
            if info.device == device:
                return info.description
        return ""

    @staticmethod
    def _port_label(info: PortInfo) -> str:
        if info.description:
            return f"{info.device} · {info.description}"
        return info.device

    def _on_port_index_changed(self, index: int) -> None:
        """把下拉项选择还原成纯设备名，列表项本身仍保留完整描述。"""
        if index < 0 or self._updating:
            return
        device = self.port_combo.itemData(index)
        if not isinstance(device, str) or not device:
            return
        editor = self.port_combo.lineEdit()
        if editor is not None and editor.text() != device:
            editor.setText(device)
            editor.setCursorPosition(len(device))
        self._update_port_tooltip()

    def _update_port_tooltip(self) -> None:
        device = self.current_port()
        description = self._description_for(device) if device else ""
        if not device:
            self.port_combo.setToolTip("")
        elif description:
            self.port_combo.setToolTip(f"{device} · {description}")
        else:
            self.port_combo.setToolTip(device)

    def _apply_popup_width(self) -> None:
        """让端口下拉弹窗按最长描述加宽，便于读完整设备名。"""
        if self.port_combo.count() == 0:
            return
        view = self.port_combo.view()
        hint = view.sizeHintForColumn(0) + 12
        view.setMinimumWidth(min(max(hint, self.port_combo.width()), 480))

    def set_refresh_active(self, active: bool) -> None:
        """按标签可见性启停端口刷新，避免后台标签持续枚举设备。"""
        if active:
            if not self._port_timer.isActive():
                self._port_timer.start()
            self._refresh_ports()
        else:
            self._port_timer.stop()

    def _refresh_ports(self) -> None:
        """按需刷新端口列表，并在端口集合未变化时直接返回。"""
        if self._controller.state not in {SessionState.DISCONNECTED, SessionState.ERROR}:
            return
        if self.port_combo.view().isVisible():
            return
        try:
            ports = tuple(self._port_provider())
        except Exception:
            return
        if ports == self._port_items:
            return
        self._port_items = ports
        editor = self.port_combo.lineEdit()
        caret = editor.cursorPosition() if editor is not None else 0
        current = self.current_port()
        with QSignalBlocker(self.port_combo):
            self.port_combo.clear()
            self._label_to_device.clear()
            for info in ports:
                label = self._port_label(info)
                self.port_combo.addItem(label, info.device)
                self._label_to_device[label] = info.device
            if current:
                index = self.port_combo.findData(current)
                if index >= 0:
                    self.port_combo.setCurrentIndex(index)
                if self.port_combo.currentText().strip() != current:
                    self.port_combo.setEditText(current)
            elif ports:
                self.port_combo.setCurrentIndex(0)
                if self.port_combo.currentText().strip() != ports[0].device:
                    self.port_combo.setEditText(ports[0].device)
            self._apply_popup_width()
        if editor is not None:
            editor.setCursorPosition(min(caret, len(editor.text())))
        self._update_port_tooltip()

    def _set_editable(self, enabled: bool) -> None:
        for widget in (
            self.port_combo,
            self.refresh_button,
            self.baud_combo,
            self.bytesize_combo,
            self.parity_combo,
            self.stopbits_combo,
            self.flow_combo,
        ):
            widget.setEnabled(enabled)

    @staticmethod
    def _select_data(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
