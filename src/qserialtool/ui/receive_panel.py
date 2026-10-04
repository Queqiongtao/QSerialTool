"""接收数据显示和显示过滤面板。"""

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QSignalBlocker, Signal
from PySide6.QtGui import QAction, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from qserialtool.domain import DisplayMode, LogRecord, SessionPreferences, TerminalScreen
from qserialtool.ui.terminal_output import TerminalOutput
from qserialtool.ui.theme_manager import CONTROL_HEIGHT_PX, data_colors, data_font

# 内存缓冲仍保留 100,000 条，界面只渲染最近若干条，避免整表重插阻塞主线程。
_MAX_RENDERED_RECORDS = 2000
_DOCUMENT_BLOCK_LIMIT = _MAX_RENDERED_RECORDS + 3

# “接收”标题与格式下拉框之间的固定间隔，参与标题行溢出宽度估算。
_HEADING_GAP = 12

# 标题行控件的折叠优先级：数值越大越先被收进“⋯”菜单；未列出的控件永不折叠。
_FOLD_RANKS: tuple[tuple[str, int], ...] = (
    ("timestamp_check", 20),
    ("rx_check", 30),
    ("tx_check", 40),
    ("pause_button", 5),
    ("clear_button", 10),
    ("highlight_check", 45),
    ("wrap_check", 50),
    ("autoscroll_check", 60),
)


@dataclass(slots=True)
class _HeaderItem:
    """标题行中一个参与宽度估算的控件。"""

    widget: QWidget
    rank: int
    mode_visible: bool = True


class _HeaderOverflow(QObject):
    """按可用宽度把次要标题行控件折叠进“⋯”菜单。

    折叠只隐藏控件并在菜单里挂一个等价动作，不搬动控件本身，勾选状态和信号连接
    因此始终只有一处来源；宽度不足时优先折叠 ``rank`` 较大的控件。
    """

    def __init__(self, panel: QWidget, layout: QHBoxLayout) -> None:
        super().__init__(panel)
        self._panel = panel
        self._layout = layout
        self._items: list[_HeaderItem] = []
        self._actions: dict[QWidget, QAction] = {}
        self._folded: set[QWidget] = set()
        self.button = QToolButton(panel)
        self.button.setText("⋯")
        self.button.setAutoRaise(True)
        self.button.setToolTip("更多显示选项")
        self.button.setFixedSize(CONTROL_HEIGHT_PX, CONTROL_HEIGHT_PX)
        self.button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu = QMenu(self.button)
        self.button.setMenu(self.menu)
        self.button.setVisible(False)

    def register(self, widget: QWidget, rank: int = 0) -> None:
        """登记标题行控件；``rank`` 大于 0 的控件可被折叠。"""
        self._items.append(_HeaderItem(widget=widget, rank=rank))
        if rank <= 0:
            return
        action = self._build_action(widget)
        self._actions[widget] = action
        self.menu.addAction(action)
        action.setVisible(False)

    def set_mode_visible(self, widget: QWidget, visible: bool) -> None:
        """记录控件是否应随视图模式显示，然后重新评估折叠。"""
        item = self._item_for(widget)
        if item is None:
            widget.setVisible(visible)
            return
        item.mode_visible = visible
        self.reflow()

    def folded_widgets(self) -> tuple[QWidget, ...]:
        """按登记顺序返回当前被收进“⋯”菜单的控件。"""
        return tuple(item.widget for item in self._items if item.widget in self._folded)

    def reflow(self) -> None:
        """按当前面板宽度决定哪些控件需要折叠。"""
        available = self._available_width()
        if available <= 0:
            return
        candidates = [item for item in self._items if item.rank > 0 and item.mode_visible]
        candidates.sort(key=lambda item: item.rank, reverse=True)
        folded: set[QWidget] = set()
        while candidates and self._required_width(folded) > available:
            folded.add(candidates.pop(0).widget)
        self._apply(folded)

    def _available_width(self) -> int:
        margins = self._layout.contentsMargins()
        return self._panel.width() - margins.left() - margins.right()

    def _required_width(self, folded: set[QWidget]) -> int:
        width = _HEADING_GAP
        shown = 0
        for item in self._items:
            if item.widget in folded or not item.mode_visible:
                continue
            width += item.widget.sizeHint().width()
            shown += 1
        spacing = self._layout.spacing()
        width += spacing * max(shown - 1, 0)
        if folded:
            width += spacing + self.button.sizeHint().width()
        return width

    def _apply(self, folded: set[QWidget]) -> None:
        self._folded = folded
        for widget, action in self._actions.items():
            item = self._item_for(widget)
            is_folded = widget in folded
            widget.setVisible(item.mode_visible and not is_folded)
            action.setVisible(is_folded)
        self.button.setVisible(bool(folded))

    def _item_for(self, widget: QWidget) -> _HeaderItem | None:
        for item in self._items:
            if item.widget is widget:
                return item
        return None

    def _build_action(self, widget: QWidget) -> QAction:
        """为折叠控件生成等价菜单动作，并与原控件双向同步。"""
        action = QAction(widget.text(), self)
        action.setToolTip(widget.toolTip())
        if isinstance(widget, QAbstractButton) and widget.isCheckable():
            action.setCheckable(True)
            action.setChecked(widget.isChecked())
            action.toggled.connect(widget.setChecked)
            widget.toggled.connect(action.setChecked)
        else:
            action.triggered.connect(widget.click)
        return action


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
        self._header_overflow = _HeaderOverflow(self, header)
        heading = QLabel("接收")
        self._heading_label = heading
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
        self.highlight_check = QCheckBox("高亮")
        self.highlight_check.setChecked(True)
        self.wrap_check = QCheckBox("自动换行")
        self.wrap_check.setChecked(True)

        self._assemble_header_row(header, heading)

        self.output = TerminalOutput()
        self.output.setPlaceholderText("暂无数据")
        self.output.setFont(data_font())
        self.output.set_wrap_enabled(self.wrap_check.isChecked())
        self.output.document().setMaximumBlockCount(_DOCUMENT_BLOCK_LIMIT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self.output)

    def _assemble_header_row(self, header: QHBoxLayout, heading: QLabel) -> None:
        """按“标题—过滤—操作”顺序装配标题行，并压到统一控件高度。"""
        header.addWidget(heading)
        header.addSpacing(_HEADING_GAP)
        header.addWidget(self.mode_combo)
        header.addWidget(self.timestamp_check)
        header.addWidget(self.rx_check)
        header.addWidget(self.tx_check)
        header.addStretch(1)
        header.addWidget(self.pause_button)
        header.addWidget(self.clear_button)
        header.addWidget(self.highlight_check)
        header.addWidget(self.wrap_check)
        header.addWidget(self.autoscroll_check)
        header.addWidget(self._header_overflow.button)
        self._register_header_widgets()
        for widget in (
            self.mode_combo,
            self.timestamp_check,
            self.rx_check,
            self.tx_check,
            self.pause_button,
            self.clear_button,
            self.highlight_check,
            self.wrap_check,
            self.autoscroll_check,
        ):
            widget.setFixedHeight(CONTROL_HEIGHT_PX)

    def _register_header_widgets(self) -> None:
        """登记标题行控件与折叠优先级，并初始化高亮开关的可见性。"""
        self._header_overflow.register(self._heading_label, 0)
        self._header_overflow.register(self.mode_combo, 0)
        for name, rank in _FOLD_RANKS:
            self._header_overflow.register(getattr(self, name), rank)
        self._header_overflow.set_mode_visible(self.highlight_check, False)

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
        self.mode_combo.setVisible(not enabled)
        # 终端视图的块状光标会盖住空态文字，切回分栏时再恢复提示。
        self.output.setPlaceholderText("" if enabled else "暂无数据")
        if not enabled:
            self._screen = None
        self.output.set_terminal_mode(enabled)
        self.output.set_highlight_enabled(self.highlight_check.isChecked())
        self.render_records()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._header_overflow.reflow()

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
        self.highlight_check.toggled.connect(self._settings_changed)
        self.wrap_check.toggled.connect(self._settings_changed)
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
                QSignalBlocker(self.highlight_check),
                QSignalBlocker(self.wrap_check),
            ):
                index = self.mode_combo.findData(preferences.display_mode)
                self.mode_combo.setCurrentIndex(max(index, 0))
                self.timestamp_check.setChecked(preferences.show_timestamp)
                self.rx_check.setChecked(preferences.show_rx)
                self.tx_check.setChecked(preferences.show_tx)
                self.autoscroll_check.setChecked(preferences.autoscroll)
                self.highlight_check.setChecked(preferences.highlight_enabled)
                self.wrap_check.setChecked(preferences.wrap_enabled)
        finally:
            self._loading = False
        self.output.set_autoscroll(self.autoscroll_check.isChecked())
        self.output.set_highlight_enabled(self.highlight_check.isChecked())
        self.output.set_wrap_enabled(self.wrap_check.isChecked())
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
        self.output.set_highlight_enabled(self.highlight_check.isChecked())
        self.output.set_wrap_enabled(self.wrap_check.isChecked())
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
