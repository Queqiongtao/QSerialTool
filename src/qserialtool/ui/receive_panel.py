"""接收数据显示和显示过滤面板。"""

from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qserialtool.domain import DisplayMode, LogRecord, SessionPreferences, TerminalScreen
from qserialtool.ui.terminal_output import TerminalOutput
from qserialtool.ui.theme_manager import data_colors, data_font

# 内存缓冲仍保留 100,000 条，界面只渲染最近若干条，避免整表重插阻塞主线程。
_MAX_RENDERED_RECORDS = 2000
_DOCUMENT_BLOCK_LIMIT = _MAX_RENDERED_RECORDS + 3


class ReceivePanel(QWidget):
    """显示当前会话的内存缓冲内容，并在终端模式承接内联输入。"""

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
        self._terminal_mode = False
        self._screen: TerminalScreen | None = None
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

        self.output = TerminalOutput()
        self.output.setFont(data_font())
        self.output.document().setMaximumBlockCount(_DOCUMENT_BLOCK_LIMIT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self.output)

    def add_leading_header_widget(self, widget: QWidget) -> None:
        """在接收标题行最左侧插入控件，例如侧栏折叠按钮。"""
        self._header_layout.insertWidget(0, widget)

    def add_trailing_header_widget(self, widget: QWidget) -> None:
        """在接收标题行末尾追加控件，例如视图模式切换按钮。"""
        self._header_layout.addWidget(widget)

    def set_terminal_mode(self, enabled: bool) -> None:
        """启用原始终端显示和日志区内联输入。"""
        self._terminal_mode = enabled
        for widget in (
            self.mode_combo,
            self.timestamp_check,
            self.rx_check,
            self.tx_check,
        ):
            widget.setVisible(not enabled)
        if not enabled:
            self._screen = None
        self.output.set_terminal_mode(enabled)
        self.render_records()

    def set_line_submit_handler(self, handler: Callable[[str], bool]) -> None:
        """设置终端行提交回调。"""
        self.output.set_submit_handler(handler)

    def set_history_provider(self, provider: Callable[[], tuple[str, ...]]) -> None:
        """设置终端输入历史提供者。"""
        self.output.set_history_provider(provider)

    def set_terminal_draft(self, text: str) -> None:
        """替换终端输入草稿。"""
        self.output.set_draft(text)

    @property
    def terminal_draft(self) -> str:
        """返回终端输入草稿。"""
        return self.output.draft

    def focus_terminal_input(self) -> None:
        """聚焦终端输入行。"""
        self.output.focus_input()

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
        self.output.set_autoscroll(self.autoscroll_check.isChecked())
        self.render_records()

    @property
    def display_mode(self) -> DisplayMode:
        """返回当前文本或 HEX 显示模式。"""
        return self.mode_combo.currentData()  # type: ignore[return-value]

    def append_record(self, record: LogRecord) -> None:
        """在未暂停时追加一条记录。"""
        if self._terminal_mode:
            if record.direction == "rx":
                screen = self._terminal_screen()
                screen.feed(record.text)
                if not self._paused:
                    self.output.render_screen(screen)
            return
        if self._paused:
            return
        if not self._should_show(record):
            return
        self.output.set_autoscroll(self.autoscroll_check.isChecked())
        self._insert_record(record)

    def render_records(self) -> None:
        """重新渲染最近的记录，超出渲染上限的部分用提示行说明。"""
        if self._paused:
            return
        records = self._records_provider()
        hidden = max(len(records) - _MAX_RENDERED_RECORDS, 0)
        self.output.set_autoscroll(self.autoscroll_check.isChecked())
        if self._terminal_mode:
            self.output.render_screen(self._terminal_screen())
            return
        self.output.begin_batch_update()
        if hidden:
            self._insert_hint(f"… 已隐藏较早的 {hidden} 条记录，导出可获取完整缓冲")
        for record in records[hidden:]:
            if self._should_show(record):
                self._insert_record(record)
        self.output.end_batch_update()

    def _terminal_screen(self) -> TerminalScreen:
        """返回终端模型；首次进入终端视图时用最近记录重建。"""
        if self._screen is None:
            self._screen = TerminalScreen()
            records = self._records_provider()
            hidden = max(len(records) - _MAX_RENDERED_RECORDS, 0)
            for record in records[hidden:]:
                if record.direction == "rx":
                    self._screen.feed(record.text)
        return self._screen

    def refresh_theme(self) -> None:
        """主题切换后按新配色重新渲染。"""
        self.render_records()

    def _insert_hint(self, text: str) -> None:
        """插入一条灰色提示行，不计入记录。"""
        self.output.append_text(text, data_colors().system)

    def _insert_record(self, record: LogRecord) -> None:
        self.output.append_text(self._format_record(record), self._color_for(record))

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
        self.output.set_autoscroll(self.autoscroll_check.isChecked())
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
        self.output.clear_content()
        if self._terminal_mode:
            self._screen = None
            self.render_records()
