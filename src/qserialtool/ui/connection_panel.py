"""串口连接参数和连接控制面板。"""

from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker, Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from qserialtool.application import SessionController
from qserialtool.domain import (
    DomainError,
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


class ConnectionPanel(QGroupBox):
    """编辑串口参数并管理单个连接。"""

    def __init__(
        self,
        *,
        controller: SessionController,
        port_provider: Callable[[], tuple[str, ...]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("串口设置", parent)
        self._controller = controller
        self._port_provider = port_provider
        self._updating = False
        self._build_ui()
        self._port_timer = QTimer(self)
        self._port_timer.setInterval(1000)
        self._port_timer.timeout.connect(self._refresh_ports)
        self._port_timer.start()
        self._refresh_ports()
        self.apply_snapshot(controller.snapshot)

    def _build_ui(self) -> None:
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(140)
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

        layout = QGridLayout(self)
        labels = (
            ("端口", self.port_combo),
            ("波特率", self.baud_combo),
            ("数据位", self.bytesize_combo),
            ("校验位", self.parity_combo),
            ("停止位", self.stopbits_combo),
            ("流控", self.flow_combo),
        )
        for index, (label_text, widget) in enumerate(labels):
            row = index // 3
            column = (index % 3) * 2
            layout.addWidget(QLabel(label_text), row, column)
            layout.addWidget(widget, row, column + 1)
        layout.addWidget(self.dtr_check, 2, 0)
        layout.addWidget(self.rts_check, 2, 1)
        layout.addWidget(self.connect_button, 2, 5, alignment=Qt.AlignmentFlag.AlignRight)

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
        finally:
            self._updating = False

    def _toggle_connection(self) -> None:
        state = self._controller.state
        try:
            if state is SessionState.CONNECTED:
                self._controller.disconnect()
            elif state in {SessionState.DISCONNECTED, SessionState.ERROR}:
                self._controller.connect(self._build_config())
        except DomainError as exc:
            QMessageBox.warning(self, "串口操作失败", exc.message)

    def _build_config(self) -> SerialConfig:
        try:
            baudrate = int(self.baud_combo.currentText().strip())
        except ValueError as exc:
            raise ValidationError("波特率必须是正整数。") from exc
        return SerialConfig(
            port=self.port_combo.currentText().strip(),
            baudrate=baudrate,
            bytesize=int(self.bytesize_combo.currentData()),
            parity=self.parity_combo.currentData(),
            stopbits=float(self.stopbits_combo.currentData()),
            flow_control=self.flow_combo.currentData(),
            dtr=self.dtr_check.isChecked(),
            rts=self.rts_check.isChecked(),
            encoding=self._controller.config.encoding,
        )

    def _line_state_changed(self) -> None:
        if self._updating or self._controller.state is not SessionState.CONNECTED:
            return
        try:
            self._controller.set_line_state(
                dtr=self.dtr_check.isChecked(),
                rts=self.rts_check.isChecked(),
            )
        except DomainError as exc:
            QMessageBox.warning(self, "线路控制失败", exc.message)

    def _refresh_ports(self) -> None:
        if self._controller.state not in {SessionState.DISCONNECTED, SessionState.ERROR}:
            return
        current = self.port_combo.currentText()
        try:
            ports = self._port_provider()
        except Exception:
            return
        self.port_combo.clear()
        self.port_combo.addItems(ports)
        if current:
            self.port_combo.setEditText(current)
        elif ports:
            self.port_combo.setCurrentIndex(0)

    def _set_editable(self, enabled: bool) -> None:
        for widget in (
            self.port_combo,
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
