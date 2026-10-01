"""发送编辑器、历史记录和周期发送面板。"""

from PySide6.QtCore import QSignalBlocker, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from qserialtool.application import SessionController
from qserialtool.domain import (
    DomainError,
    LineEnding,
    SessionPreferences,
    SessionState,
    append_line_ending,
    encode_text,
    parse_hex,
)

_NEWLINES: tuple[tuple[str, LineEnding], ...] = (
    ("无换行", "none"),
    ("CR", "cr"),
    ("LF", "lf"),
    ("CRLF", "crlf"),
)


class SendPanel(QWidget):
    """编辑并发送文本或 HEX 数据。"""

    preferences_changed = Signal()

    def __init__(
        self,
        *,
        controller: SessionController,
        preferences: SessionPreferences | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._history: list[str] = []
        self._connected = False
        self._loading = False
        self._build_ui()
        self._connect_changes()
        if preferences is not None:
            self.apply_preferences(preferences)
        self.set_connected(controller.state is SessionState.CONNECTED)

    def _build_ui(self) -> None:
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("发送格式"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("文本", "text")
        self.mode_combo.addItem("HEX", "hex")
        toolbar.addWidget(self.mode_combo)
        toolbar.addWidget(QLabel("换行"))
        self.newline_combo = QComboBox()
        for label, value in _NEWLINES:
            self.newline_combo.addItem(label, value)
        toolbar.addWidget(self.newline_combo)
        toolbar.addWidget(QLabel("历史"))
        self.history_combo = QComboBox()
        self.history_combo.setMinimumWidth(160)
        toolbar.addWidget(self.history_combo)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(10, 86_400_000)
        self.interval_spin.setValue(1000)
        self.interval_spin.setSuffix(" ms")
        toolbar.addWidget(self.interval_spin)
        self.periodic_button = QPushButton("开始周期")
        self.periodic_button.setCheckable(True)
        toolbar.addWidget(self.periodic_button)
        toolbar.addStretch(1)
        self.send_button = QPushButton("发送")
        self.send_button.setToolTip("Ctrl+Enter")
        self.send_button.clicked.connect(self.send)
        toolbar.addWidget(self.send_button)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("输入待发送内容，按 Ctrl+Enter 发送")
        self.editor.setMinimumHeight(80)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toolbar)
        layout.addWidget(self.editor)

        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.editor)
        shortcut.activated.connect(self.send)
        self._periodic_timer = QTimer(self)
        self._periodic_timer.timeout.connect(self._periodic_tick)

    def _connect_changes(self) -> None:
        self.mode_combo.currentIndexChanged.connect(self._settings_changed)
        self.newline_combo.currentIndexChanged.connect(self._settings_changed)
        self.interval_spin.valueChanged.connect(self._settings_changed)
        self.history_combo.activated.connect(self._history_selected)
        self.periodic_button.toggled.connect(self._periodic_toggled)

    def apply_preferences(self, preferences: SessionPreferences) -> None:
        """应用持久化的发送偏好和历史。"""
        self._loading = True
        try:
            with (
                QSignalBlocker(self.mode_combo),
                QSignalBlocker(self.newline_combo),
                QSignalBlocker(self.interval_spin),
            ):
                mode_index = self.mode_combo.findData(preferences.send_mode)
                self.mode_combo.setCurrentIndex(max(mode_index, 0))
                newline_index = self.newline_combo.findData(preferences.line_ending)
                self.newline_combo.setCurrentIndex(max(newline_index, 0))
                self.interval_spin.setValue(preferences.periodic_interval_ms)
            self._history = list(preferences.send_history)
            self._update_history_combo()
        finally:
            self._loading = False

    @property
    def history(self) -> tuple[str, ...]:
        """返回按发送顺序排列的历史内容。"""
        return tuple(self._history)

    def set_connected(self, connected: bool) -> None:
        """根据连接状态启用发送控件。"""
        self._connected = connected
        self.send_button.setEnabled(connected)
        self.periodic_button.setEnabled(connected)
        if not connected and self.periodic_button.isChecked():
            self.periodic_button.setChecked(False)

    def send(self) -> None:
        """手动发送当前内容。"""
        self._send_current(remember=True)

    def _send_current(self, *, remember: bool) -> bool:
        content = self.editor.toPlainText()
        try:
            self._controller.send(self._build_payload())
        except DomainError as exc:
            QMessageBox.warning(self, "发送失败", exc.message)
            return False
        if remember and content:
            self._remember_history(content)
        return True

    def _build_payload(self) -> bytes:
        content = self.editor.toPlainText()
        mode = self.mode_combo.currentData()
        if mode == "hex":
            data = parse_hex(content)
        else:
            data = encode_text(content, self._controller.config.encoding)
        return append_line_ending(data, self.newline_combo.currentData())

    def _remember_history(self, content: str) -> None:
        if self._history and self._history[-1] == content:
            return
        self._history.append(content)
        self._history = self._history[-100:]
        self._update_history_combo()
        self.preferences_changed.emit()

    def _update_history_combo(self) -> None:
        with QSignalBlocker(self.history_combo):
            self.history_combo.clear()
            self.history_combo.addItem("选择历史", None)
            for item in reversed(self._history):
                self.history_combo.addItem(item.replace("\n", "\\n")[:80], item)

    def _history_selected(self, index: int) -> None:
        if index <= 0:
            return
        content = self.history_combo.itemData(index)
        if isinstance(content, str):
            self.editor.setPlainText(content)

    def _settings_changed(self) -> None:
        if not self._loading:
            self.preferences_changed.emit()

    def _periodic_toggled(self, enabled: bool) -> None:
        if enabled:
            if not self._connected or not self.editor.toPlainText():
                self._loading = True
                self.periodic_button.setChecked(False)
                self._loading = False
                return
            self._periodic_timer.start(self.interval_spin.value())
            self.periodic_button.setText("停止周期")
        else:
            self._periodic_timer.stop()
            self.periodic_button.setText("开始周期")

    def _periodic_tick(self) -> None:
        if not self._send_current(remember=False):
            self.periodic_button.setChecked(False)

    def closeEvent(self, event: object) -> None:
        self._periodic_timer.stop()
        super().closeEvent(event)
