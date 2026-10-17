"""接收数据显示和显示过滤面板。"""

from collections.abc import Callable

from PySide6.QtCore import QElapsedTimer, QEvent, QObject, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QResizeEvent
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
from qserialtool.ui.icons import set_action_icon, svg_icon
from qserialtool.ui.receive_format import record_segments, should_show
from qserialtool.ui.receive_header import FOLD_RANKS, HeaderOverflow, assemble_header_row
from qserialtool.ui.terminal_output import TerminalOutput
from qserialtool.ui.theme_manager import data_colors, data_font

# 内存缓冲仍保留 100,000 条，界面只渲染最近若干条，避免整表重插阻塞主线程。
_MAX_RENDERED_RECORDS = 2000
_DOCUMENT_BLOCK_LIMIT = _MAX_RENDERED_RECORDS + 3

# 高频数据流的渲染合并窗口：空闲后的第一条立即显示，其余在同一窗口内合并成一帧。
_FLUSH_INTERVAL_MS = 30

# 分栏空态的居中提示；终端视图或已有内容时隐藏。
_EMPTY_TITLE = "暂无数据"
_EMPTY_HINT = "连接成功后，接收内容会显示在这里"


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
        self._pending_records: list[LogRecord] = []
        self._last_flush: QElapsedTimer | None = None
        self._flush_timer = QTimer(self)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.timeout.connect(self._flush_pending)
        self._build_ui()
        self._connect_changes()
        if preferences is not None:
            self.apply_preferences(preferences)
        self.render_records()

    def _build_ui(self) -> None:
        header = QHBoxLayout()
        header.setSpacing(6)
        self._header_layout = header
        self._header_overflow = HeaderOverflow(self, header)
        # 标题行控件创建时即挂到面板上：HeaderOverflow 在控件进入布局之前就会
        # 通过 setVisible() 写入可见性，而无父控件的 setVisible(True) 会被 Qt
        # 显示成带系统标题栏的顶层窗口（启动期小窗闪烁，见 receive_header）。
        heading = QLabel("接收", self)
        heading.setObjectName("panelHeading")
        self._heading_label = heading
        heading_font = heading.font()
        heading_font.setBold(True)
        heading.setFont(heading_font)
        self.mode_combo = QComboBox(self)
        self.mode_combo.addItem("文本", "text")
        self.mode_combo.addItem("HEX", "hex")
        self.timestamp_check = QCheckBox("时间戳", self)
        self.timestamp_check.setChecked(True)
        self.terminal_timestamp_check = QCheckBox("时间戳", self)
        self.rx_check = QCheckBox("RX", self)
        self.rx_check.setChecked(True)
        self.tx_check = QCheckBox("TX", self)
        self.tx_check.setChecked(True)
        self.pause_button = QPushButton("暂停", self)
        self.pause_button.setCheckable(True)
        set_action_icon(self.pause_button, "pause")
        self.clear_button = QPushButton("清屏", self)
        set_action_icon(self.clear_button, "eraser")
        self.autoscroll_check = QCheckBox("自动滚动", self)
        self.autoscroll_check.setChecked(True)
        self.highlight_check = QCheckBox("高亮", self)
        self.highlight_check.setChecked(True)
        self.wrap_check = QCheckBox("自动换行", self)
        self.wrap_check.setChecked(True)

        self._register_header_widgets()
        assemble_header_row(
            header,
            heading=heading,
            filters=(
                self.mode_combo,
                self.timestamp_check,
                self.terminal_timestamp_check,
                self.rx_check,
                self.tx_check,
            ),
            controls=(
                self.pause_button,
                self.clear_button,
                self.highlight_check,
                self.wrap_check,
                self.autoscroll_check,
            ),
            overflow=self._header_overflow,
        )

        self.output = TerminalOutput()
        self.output.setFont(data_font())
        self.output.set_wrap_enabled(self.wrap_check.isChecked())
        self.output.document().setMaximumBlockCount(_DOCUMENT_BLOCK_LIMIT)
        self.empty_state = QLabel(self.output.viewport())
        self.empty_state.setObjectName("emptyState")
        self.empty_state.setText(f"<b>{_EMPTY_TITLE}</b><br>{_EMPTY_HINT}")
        self.empty_state.setTextFormat(Qt.TextFormat.RichText)
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 覆盖层只做提示：连同子级不接收鼠标事件，不影响选中与滚动。
        self.empty_state.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.empty_state.hide()
        self.output.viewport().installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self.output)

    def _register_header_widgets(self) -> None:
        """登记标题行控件与折叠优先级，并初始化按模式显示的开关可见性。"""
        self._header_overflow.register(self._heading_label, 0)
        self._header_overflow.register(self.mode_combo, 0)
        for name, rank in FOLD_RANKS:
            self._header_overflow.register(getattr(self, name), rank)
        self._header_overflow.set_mode_visible(self.highlight_check, False)
        self._header_overflow.set_mode_visible(self.terminal_timestamp_check, False)

    def add_leading_header_widget(self, widget: QWidget, *, fold_rank: int = 0) -> None:
        """在接收标题行最左侧插入控件，例如侧栏折叠按钮。"""
        self._header_layout.insertWidget(0, widget)
        self._header_overflow.register(widget, fold_rank)
        self._header_overflow.reflow()

    def add_trailing_header_widget(self, widget: QWidget, *, fold_rank: int = 0) -> None:
        """在接收标题行末尾插入控件，例如视图模式切换按钮。"""
        self._header_layout.insertWidget(self._header_layout.count() - 1, widget)
        self._header_overflow.register(widget, fold_rank)
        self._header_overflow.reflow()

    def set_terminal_mode(self, enabled: bool) -> None:
        """启用原始终端显示和日志区内联输入。"""
        self._terminal_mode = enabled
        for widget in (self.timestamp_check, self.rx_check, self.tx_check):
            self._header_overflow.set_mode_visible(widget, not enabled)
        self._header_overflow.set_mode_visible(self.highlight_check, enabled)
        self._header_overflow.set_mode_visible(self.terminal_timestamp_check, enabled)
        self.mode_combo.setVisible(not enabled)
        if not enabled:
            self._screen = None
        self.output.set_terminal_mode(enabled)
        self.output.set_highlight_enabled(self.highlight_check.isChecked())
        self.render_records()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """输出视口尺寸变化时把空态提示重新居中。"""
        if watched is self.output.viewport() and event.type() is QEvent.Type.Resize:
            self._place_empty_state()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._header_overflow.reflow()

    def set_line_submit_handler(self, handler: Callable[[str], bool]) -> None:
        """设置终端行提交回调。"""
        self.output.set_submit_handler(handler)

    def set_history_provider(self, provider: Callable[[], tuple[str, ...]]) -> None:
        """设置终端输入历史提供者。"""
        self.output.set_history_provider(provider)

    def set_raw_send_handler(self, handler: Callable[[bytes], bool]) -> None:
        """设置终端按键透传的原始字节发送回调。"""
        self.output.set_raw_send_handler(handler)

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
        self.highlight_check.toggled.connect(self._settings_changed)
        self.wrap_check.toggled.connect(self._settings_changed)
        self.terminal_timestamp_check.toggled.connect(self._settings_changed)
        self.pause_button.toggled.connect(self._pause_changed)
        self.clear_button.clicked.connect(self._clear)

    def apply_preferences(self, preferences: SessionPreferences) -> None:
        """应用持久化的显示偏好。"""
        self._loading = True
        try:
            with (
                QSignalBlocker(self.mode_combo),
                QSignalBlocker(self.timestamp_check),
                QSignalBlocker(self.terminal_timestamp_check),
                QSignalBlocker(self.rx_check),
                QSignalBlocker(self.tx_check),
                QSignalBlocker(self.autoscroll_check),
                QSignalBlocker(self.highlight_check),
                QSignalBlocker(self.wrap_check),
            ):
                index = self.mode_combo.findData(preferences.display_mode)
                self.mode_combo.setCurrentIndex(max(index, 0))
                self.timestamp_check.setChecked(preferences.show_timestamp)
                self.terminal_timestamp_check.setChecked(preferences.terminal_timestamp)
                self.rx_check.setChecked(preferences.show_rx)
                self.tx_check.setChecked(preferences.show_tx)
                self.autoscroll_check.setChecked(preferences.autoscroll)
                self.highlight_check.setChecked(preferences.highlight_enabled)
                self.wrap_check.setChecked(preferences.wrap_enabled)
        finally:
            self._loading = False
        self.output.set_autoscroll(self.autoscroll_check.isChecked())
        self.output.set_highlight_enabled(self.highlight_check.isChecked())
        self.output.set_show_timestamps(self.terminal_timestamp_check.isChecked())
        self.output.set_wrap_enabled(self.wrap_check.isChecked())
        self.render_records()

    @property
    def display_mode(self) -> DisplayMode:
        """返回当前文本或 HEX 显示模式。"""
        return self.mode_combo.currentData()  # type: ignore[return-value]

    def append_record(self, record: LogRecord) -> None:
        """在未暂停时追加一条记录；高频到达时按合并窗口批量渲染。"""
        if self._terminal_mode:
            if record.direction == "rx":
                screen = self._terminal_screen()
                screen.feed(record.text, timestamp=record.timestamp_utc)
                if not self._paused:
                    self._schedule_flush()
            return
        if self._paused:
            return
        if not self._should_show(record):
            return
        self._pending_records.append(record)
        self._schedule_flush()

    def _schedule_flush(self) -> None:
        """空闲后的第一条立即渲染，其余记录在合并窗口内攒成一帧。"""
        elapsed = self._last_flush.elapsed() if self._last_flush is not None else None
        if elapsed is None or elapsed >= _FLUSH_INTERVAL_MS:
            self._flush_pending()
            return
        if not self._flush_timer.isActive():
            self._flush_timer.start(_FLUSH_INTERVAL_MS - elapsed)

    def _flush_pending(self) -> None:
        """渲染自上一帧以来到达的记录。"""
        self._flush_timer.stop()
        if self._last_flush is None:
            self._last_flush = QElapsedTimer()
            self._last_flush.start()
        else:
            self._last_flush.restart()
        if self._terminal_mode:
            if not self._paused:
                self._render_terminal_screen()
            return
        records, self._pending_records = self._pending_records, []
        if not records:
            return
        self.output.set_autoscroll(self.autoscroll_check.isChecked())
        self.output.append_lines([self._record_segments(record) for record in records])
        self._sync_empty_state()

    def _discard_pending(self) -> None:
        """丢弃尚未渲染的记录；调用方随后必须自行重绘或清屏。"""
        self._flush_timer.stop()
        self._pending_records.clear()

    def _render_terminal_screen(self, *, full: bool = False) -> None:
        """渲染终端画面；整屏重建只用于主题、高亮或过滤变化。"""
        self.output.set_autoscroll(self.autoscroll_check.isChecked())
        self.output.render_screen(self._terminal_screen(), full=full)

    def render_records(self) -> None:
        """重新渲染最近的记录，超出渲染上限的部分用提示行说明。"""
        if self._paused:
            return
        self._render_records()
        self._sync_empty_state()

    def _render_records(self) -> None:
        self._discard_pending()
        records = self._records_provider()
        hidden = max(len(records) - _MAX_RENDERED_RECORDS, 0)
        self.output.set_autoscroll(self.autoscroll_check.isChecked())
        if self._terminal_mode:
            self._render_terminal_screen(full=True)
            return
        self.output.begin_batch_update()
        if hidden:
            self._insert_hint(f"… 已隐藏较早的 {hidden} 条记录，导出可获取完整缓冲")
        for record in records[hidden:]:
            if self._should_show(record):
                self._insert_record(record)
        self.output.end_batch_update()

    def _sync_empty_state(self) -> None:
        """按分栏/终端模式与文档是否为空更新空态提示。"""
        visible = not self._terminal_mode and self.output.document().isEmpty()
        self.empty_state.setVisible(visible)
        if visible:
            self._place_empty_state()

    def _place_empty_state(self) -> None:
        """把空态提示居中放到输出视口。"""
        self.empty_state.adjustSize()
        viewport_rect = self.output.viewport().rect()
        size = self.empty_state.size()
        self.empty_state.move(
            viewport_rect.center().x() - size.width() // 2,
            viewport_rect.center().y() - size.height() // 2,
        )

    def _terminal_screen(self) -> TerminalScreen:
        """返回终端模型；首次进入终端视图时用最近记录重建。"""
        if self._screen is None:
            self._screen = TerminalScreen()
            records = self._records_provider()
            hidden = max(len(records) - _MAX_RENDERED_RECORDS, 0)
            for record in records[hidden:]:
                if record.direction == "rx":
                    self._screen.feed(record.text, timestamp=record.timestamp_utc)
        return self._screen

    def set_data_font_size(self, size: int) -> None:
        """按全局字号更新接收区字体。"""
        self.output.setFont(data_font(size))

    def refresh_theme(self) -> None:
        """主题切换后按新配色重新渲染。"""
        self.render_records()

    def _insert_hint(self, text: str) -> None:
        """插入一条灰色提示行，不计入记录。"""
        self.output.append_text(text, data_colors().system)

    def _insert_record(self, record: LogRecord) -> None:
        self.output.append_segments(self._record_segments(record))

    def _record_segments(self, record: LogRecord) -> tuple[tuple[str, str, bool], ...]:
        """按当前标题行状态把记录拆成 (文本, 颜色, 加粗) 片段。"""
        return record_segments(
            record,
            show_timestamp=self.timestamp_check.isChecked(),
            display_mode=self.display_mode,
        )

    def _should_show(self, record: LogRecord) -> bool:
        return should_show(
            record,
            show_rx=self.rx_check.isChecked(),
            show_tx=self.tx_check.isChecked(),
        )

    def _settings_changed(self) -> None:
        if self._loading:
            return
        self.output.set_autoscroll(self.autoscroll_check.isChecked())
        self.output.set_highlight_enabled(self.highlight_check.isChecked())
        self.output.set_show_timestamps(self.terminal_timestamp_check.isChecked())
        self.output.set_wrap_enabled(self.wrap_check.isChecked())
        self.render_records()
        self.preferences_changed.emit()

    def _pause_changed(self, paused: bool) -> None:
        self._paused = paused
        self.pause_button.setText("继续" if paused else "暂停")
        self.pause_button.setIcon(svg_icon("play" if paused else "pause"))
        if paused:
            self._discard_pending()
        else:
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
        self._discard_pending()
        self.output.clear_content()
        if self._terminal_mode:
            self._screen = None
            self.render_records()
        else:
            self._sync_empty_state()

    def request_clear(self) -> None:
        """请求清空接收区；走与“清屏”按钮相同的确认与重置流程。"""
        self._clear()
