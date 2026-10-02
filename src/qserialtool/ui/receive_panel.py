"""接收数据显示和显示过滤面板。"""

from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qserialtool.domain import DisplayMode, LogRecord, SessionPreferences
from qserialtool.ui.theme_manager import data_colors, data_font

# 内存缓冲仍保留 100,000 条，界面只渲染最近若干条，避免整表重插阻塞主线程。
_MAX_RENDERED_RECORDS = 2000
_DOCUMENT_BLOCK_LIMIT = _MAX_RENDERED_RECORDS + 2


class ReceivePanel(QWidget):
    """显示当前会话的内存缓冲内容。"""

    preferences_changed = Signal()

    def __init__(
        self,
        *,
        records_provider: Callable[[], tuple[LogRecord, ...]],
        clear_callback: Callable[[], int],
        preferences: SessionPreferences | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._records_provider = records_provider
        self._clear_callback = clear_callback
        self._paused = False
        self._loading = False
        self._build_ui()
        self._connect_changes()
        if preferences is not None:
            self.apply_preferences(preferences)
        self.render_records()

    def _build_ui(self) -> None:
        header = QHBoxLayout()
        header.setSpacing(6)
        self._header_layout = header
        heading = QLabel("接收")
        heading_font = heading.font()
        heading_font.setBold(True)
        heading.setFont(heading_font)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("文本", "text")
        self.mode_combo.addItem("HEX", "hex")
        self.timestamp_check = QCheckBox("时间戳")
        self.timestamp_check.setChecked(True)
        self.rx_check = QCheckBox("RX")
        self.rx_check.setChecked(True)
        self.tx_check = QCheckBox("TX")
        self.tx_check.setChecked(True)
        self.pause_button = QPushButton("暂停")
        self.pause_button.setCheckable(True)
        self.clear_button = QPushButton("清屏")
        self.autoscroll_check = QCheckBox("自动滚动")
        self.autoscroll_check.setChecked(True)

        header.addWidget(heading)
        header.addSpacing(12)
        header.addWidget(self.mode_combo)
        header.addWidget(self.timestamp_check)
        header.addWidget(self.rx_check)
        header.addWidget(self.tx_check)
        header.addStretch(1)
        header.addWidget(self.pause_button)
        header.addWidget(self.clear_button)
        header.addWidget(self.autoscroll_check)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(data_font())
        self.output.document().setMaximumBlockCount(_DOCUMENT_BLOCK_LIMIT)
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output.setMinimumHeight(140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self.output)

    def add_leading_header_widget(self, widget: QWidget) -> None:
        """在接收标题行最左侧插入控件，例如侧栏折叠按钮。"""
        self._header_layout.insertWidget(0, widget)

    def _connect_changes(self) -> None:
        self.mode_combo.currentIndexChanged.connect(self._settings_changed)
        self.timestamp_check.toggled.connect(self._settings_changed)
        self.rx_check.toggled.connect(self._settings_changed)
        self.tx_check.toggled.connect(self._settings_changed)
        self.autoscroll_check.toggled.connect(self._settings_changed)
        self.pause_button.toggled.connect(self._pause_changed)
        self.clear_button.clicked.connect(self._clear)

    def apply_preferences(self, preferences: SessionPreferences) -> None:
        """应用持久化的显示偏好。"""
        self._loading = True
        try:
            with (
                QSignalBlocker(self.mode_combo),
                QSignalBlocker(self.timestamp_check),
                QSignalBlocker(self.rx_check),
                QSignalBlocker(self.tx_check),
                QSignalBlocker(self.autoscroll_check),
            ):
                index = self.mode_combo.findData(preferences.display_mode)
                self.mode_combo.setCurrentIndex(max(index, 0))
                self.timestamp_check.setChecked(preferences.show_timestamp)
                self.rx_check.setChecked(preferences.show_rx)
                self.tx_check.setChecked(preferences.show_tx)
                self.autoscroll_check.setChecked(preferences.autoscroll)
        finally:
            self._loading = False
        self.render_records()

    @property
    def display_mode(self) -> DisplayMode:
        """返回当前文本或 HEX 显示模式。"""
        return self.mode_combo.currentData()  # type: ignore[return-value]

    def append_record(self, record: LogRecord) -> None:
        """在未暂停时追加一条记录。"""
        if self._paused or not self._should_show(record):
            return
        self._insert_record(record)

    def render_records(self) -> None:
        """重新渲染最近的记录，超出渲染上限的部分用提示行说明。"""
        if self._paused:
            return
        records = self._records_provider()
        hidden = max(len(records) - _MAX_RENDERED_RECORDS, 0)
        self.output.clear()
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if hidden:
            self._insert_hint(cursor, f"… 已隐藏较早的 {hidden} 条记录，导出可获取完整缓冲")
        for record in records[hidden:]:
            if self._should_show(record):
                self._insert_record(record, cursor)
        if self.autoscroll_check.isChecked():
            self.output.moveCursor(QTextCursor.MoveOperation.End)

    def refresh_theme(self) -> None:
        """主题切换后按新配色重新渲染。"""
        self.render_records()

    def _insert_hint(self, cursor: QTextCursor, text: str) -> None:
        """插入一条灰色提示行，不计入记录。"""
        text_format = QTextCharFormat()
        text_format.setForeground(QColor(data_colors().system))
        cursor.setCharFormat(text_format)
        cursor.insertText(text + "\n")

    def _insert_record(
        self,
        record: LogRecord,
        cursor: QTextCursor | None = None,
    ) -> None:
        target = cursor or self.output.textCursor()
        if cursor is None:
            target.movePosition(QTextCursor.MoveOperation.End)
        text_format = QTextCharFormat()
        text_format.setForeground(QColor(self._color_for(record)))
        target.setCharFormat(text_format)
        target.insertText(self._format_record(record) + "\n")
        if cursor is None and self.autoscroll_check.isChecked():
            self.output.moveCursor(QTextCursor.MoveOperation.End)

    def _format_record(self, record: LogRecord) -> str:
        prefix = ""
        if self.timestamp_check.isChecked():
            local_time = record.timestamp_utc.astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            prefix += f"[{local_time}] "
        prefix += f"{record.direction.upper()}: "
        payload = record.hex_text if self.display_mode == "hex" else record.text
        return prefix + payload

    def _should_show(self, record: LogRecord) -> bool:
        if record.direction == "rx":
            return self.rx_check.isChecked()
        if record.direction == "tx":
            return self.tx_check.isChecked()
        return True

    def _color_for(self, record: LogRecord) -> str:
        colors = data_colors()
        if record.direction == "rx":
            return colors.rx
        if record.direction == "tx":
            return colors.tx
        return colors.system

    def _settings_changed(self) -> None:
        if self._loading:
            return
        self.render_records()
        self.preferences_changed.emit()

    def _pause_changed(self, paused: bool) -> None:
        self._paused = paused
        self.pause_button.setText("继续" if paused else "暂停")
        if not paused:
            self.render_records()

    def _clear(self) -> None:
        if (
            self._records_provider()
            and QMessageBox.question(
                self,
                "清空接收区",
                "确定清空当前内存缓冲吗？自动日志文件不会受影响。",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._clear_callback()
        self.output.clear()
