"""终端视图控件：渲染终端网格并提供光标处的内联输入。"""

from collections.abc import Callable, Sequence

from PySide6.QtCore import QEvent, QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QContextMenuEvent,
    QFocusEvent,
    QHideEvent,
    QInputMethodEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QShowEvent,
    QTextCursor,
    QTextOption,
)
from PySide6.QtWidgets import QMenu, QPlainTextEdit, QWidget

from qserialtool.domain import TerminalInputMode, TerminalScreen
from qserialtool.ui.terminal_inline_input import TerminalInlineInput
from qserialtool.ui.terminal_render_format import text_format
from qserialtool.ui.terminal_screen_renderer import TerminalScreenRenderer

# 块状光标的闪烁周期（毫秒）；与 Windows 控制台、xterm 默认的 530ms 一致。
_CURSOR_BLINK_MS = 530

# 纯修饰键不应清空选区或产生发送；Qt 会为按下修饰键单独派发 KeyPress。
_MODIFIER_KEYS = frozenset(
    {
        Qt.Key.Key_Shift,
        Qt.Key.Key_Control,
        Qt.Key.Key_Alt,
        Qt.Key.Key_AltGr,
        Qt.Key.Key_Meta,
        Qt.Key.Key_Super_L,
        Qt.Key.Key_Super_R,
        Qt.Key.Key_Hyper_L,
        Qt.Key.Key_CapsLock,
        Qt.Key.Key_NumLock,
        Qt.Key.Key_ScrollLock,
    }
)


class TerminalOutput(QPlainTextEdit):
    """渲染终端网格，并支持行缓冲草稿或逐键发送两种输入方式。"""

    copied = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._terminal_mode = False
        self._raw_input_enabled = True
        self._autoscroll = True
        self._batch_update = False
        self._scrolling = False
        self._mouse_selecting = False
        self._cursor_visible = True
        self._cursor_blink_timer = QTimer(self)
        self._cursor_blink_timer.setInterval(_CURSOR_BLINK_MS)
        self._cursor_blink_timer.timeout.connect(self._blink_cursor)
        self._input = TerminalInlineInput(
            self,
            after_edit=self._after_terminal_update,
            is_ready=lambda: self._renderer.has_screen,
        )
        self._renderer = TerminalScreenRenderer(
            self,
            self._input,
            after_update=self._after_terminal_update,
            should_defer=self._should_defer_render,
        )
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setAcceptDrops(False)
        self.setCursorWidth(0)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.selectionChanged.connect(self._on_selection_changed)

    @property
    def draft(self) -> str:
        """返回当前终端输入草稿；逐键模式始终为空。"""
        return self._input.draft

    @property
    def input_mode(self) -> TerminalInputMode:
        """返回当前终端输入模式。"""
        return self._input.mode

    def set_input_mode(self, mode: TerminalInputMode) -> None:
        """切换行缓冲/逐键发送模式。"""
        self._input.set_mode(mode)

    def set_raw_input_enabled(self, enabled: bool) -> None:
        """在未连接时关闭逐键发送，避免每个按键都弹出错误提示。"""
        self._raw_input_enabled = enabled

    def set_terminal_mode(self, enabled: bool) -> None:
        """启用或关闭终端网格渲染与内联输入。"""
        if self._terminal_mode == enabled:
            return
        self._terminal_mode = enabled
        self._renderer.reset_for_mode()
        self._input.set_enabled(enabled)
        super().clear()
        self.setReadOnly(not enabled)
        self._sync_cursor_blink()

    def set_submit_handler(self, handler: Callable[[str], bool]) -> None:
        """设置行提交回调；返回 False 时保留输入草稿。"""
        self._input.set_submit_handler(handler)

    def set_history_provider(self, provider: Callable[[], tuple[str, ...]]) -> None:
        """设置发送历史读取函数。"""
        self._input.set_history_provider(provider)

    def set_raw_send_handler(self, handler: Callable[[bytes], bool]) -> None:
        """设置原始字节发送回调，用于终端方向键等按键透传。"""
        self._input.set_raw_send_handler(handler)

    def set_text_send_handler(self, handler: Callable[[str], bool]) -> None:
        """设置逐键模式的文本发送回调。"""
        self._input.set_text_send_handler(handler)

    def set_autoscroll(self, enabled: bool) -> None:
        """设置新记录到达时是否自动滚动。"""
        self._autoscroll = enabled

    def set_highlight_enabled(self, enabled: bool) -> None:
        """设置是否在终端视图中叠加地址、链接与关键字高亮。"""
        self._renderer.set_highlight_enabled(enabled)

    def set_show_timestamps(self, enabled: bool) -> None:
        """设置是否在终端每行前渲染灰色的到达时间前缀。"""
        self._renderer.set_show_timestamps(enabled)

    def set_wrap_enabled(self, enabled: bool) -> None:
        """设置超长行是否按控件宽度自动换行。"""
        if enabled:
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            self.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        else:
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def set_draft(self, text: str) -> None:
        """替换终端草稿，供历史菜单回填。"""
        self._input.set_draft(text)
        self.focus_input()

    def focus_input(self) -> None:
        """把焦点和光标移到输入草稿末尾。"""
        if not self._terminal_mode:
            return
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        if self._renderer.has_screen:
            self._input.place_cursor()
            self.ensureCursorVisible()

    def begin_batch_update(self) -> None:
        """分栏视图批量追加期间暂停滚动。"""
        self._batch_update = True

    def end_batch_update(self) -> None:
        """结束批量追加并滚动到末尾。"""
        self._batch_update = False
        self._scroll_after_update()

    def clear_content(self) -> None:
        """清空控件内容；终端模式由调用方随后重建画面。"""
        self._renderer.cancel_deferred()
        self._renderer.invalidate()
        super().clear()
        self._input.reset_anchor()
        self._sync_cursor_blink()

    def append_text(self, text: str, color: str) -> None:
        """按单色追加一行文本，供提示行等简单调用方使用。"""
        self.append_segments(((text, color, False),))

    def append_segments(self, segments: Sequence[tuple[str, str, bool]]) -> None:
        """按 (文本, 颜色, 是否加粗) 片段追加一行，行尾用默认文本色换行。"""
        self.append_lines((segments,))

    def append_lines(self, lines: Sequence[Sequence[tuple[str, str, bool]]]) -> None:
        """在一个编辑块内追加多行，行尾用默认文本色换行，供批量记录合并渲染。"""
        if not lines:
            return
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        default_color = self.palette().color(QPalette.ColorRole.Text).name()
        cursor.beginEditBlock()
        for segments in lines:
            for text, color, bold in segments:
                if not text:
                    continue
                cursor.setCharFormat(text_format(color, bold))
                cursor.insertText(text)
            cursor.setCharFormat(text_format(default_color))
            cursor.insertText("\n")
        cursor.endEditBlock()
        if not self._batch_update:
            self._scroll_after_update()

    def render_screen(self, screen: TerminalScreen, *, full: bool = False) -> None:
        """按终端模型更新画面，并在光标处渲染输入草稿。

        ``full=True`` 丢弃增量状态强制整屏重建，供主题、高亮或过滤变化后调用。
        """
        if not self._terminal_mode:
            return
        self._renderer.render(screen, full=full)

    def paintEvent(self, event: QPaintEvent) -> None:
        """在草稿末尾绘制闪烁的块状光标，避免污染正文内容。"""
        super().paintEvent(event)
        if not self._terminal_mode or not self._renderer.has_screen or not self._cursor_visible:
            return
        caret = QTextCursor(self.document())
        caret.setPosition(self._input.bounds()[1])
        rect = self.cursorRect(caret)
        width = max(self.fontMetrics().horizontalAdvance(" "), 1)
        painter = QPainter(self.viewport())
        painter.fillRect(
            QRect(rect.left(), rect.top(), width, rect.height()),
            self.palette().color(QPalette.ColorRole.Text),
        )

    def _should_defer_render(self) -> bool:
        return self._mouse_selecting or self.textCursor().hasSelection()

    def _after_terminal_update(self) -> None:
        """输入或渲染完成后重置光标闪烁相位，并恢复自动滚动。"""
        self._touch_cursor()
        self._scroll_after_update()

    def _touch_cursor(self) -> None:
        """让光标立即显示并重新计时，供输入、渲染、聚焦与失焦时调用。"""
        if not self._cursor_visible:
            self._cursor_visible = True
            self.viewport().update()
        self._sync_cursor_blink()

    def _sync_cursor_blink(self) -> None:
        """按终端状态、画面模型、可见性与焦点启停闪烁定时器。"""
        if self._cursor_blink_active():
            if not self._cursor_blink_timer.isActive():
                self._cursor_blink_timer.start()
        else:
            self._cursor_blink_timer.stop()

    def _cursor_blink_active(self) -> bool:
        return (
            self._terminal_mode
            and self._renderer.has_screen
            and self.isVisible()
            and self.hasFocus()
        )

    def _blink_cursor(self) -> None:
        """闪烁定时器回调：翻转光标可见性并重绘视口；条件不再满足时自停。"""
        if not self._cursor_blink_active():
            self._cursor_blink_timer.stop()
            return
        self._cursor_visible = not self._cursor_visible
        self.viewport().update()

    def _scroll_after_update(self) -> None:
        """自动滚动到末尾；存在选中内容、鼠标拖选或正在滚动时保持原位。"""
        if not self._autoscroll or self._scrolling or self._mouse_selecting:
            return
        if self.textCursor().hasSelection():
            return
        self._scrolling = True
        try:
            self.moveCursor(QTextCursor.MoveOperation.End)
            self.ensureCursorVisible()
        finally:
            self._scrolling = False

    def _on_selection_changed(self) -> None:
        """选中被清除后补上暂停期间延迟的渲染与自动滚动。"""
        if self._scrolling or self._mouse_selecting or self.textCursor().hasSelection():
            return
        if self._renderer.flush_deferred():
            self._scroll_after_update()

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self._touch_cursor()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        """失焦后停止闪烁但保持实心光标，输入位置提示不消失。"""
        super().focusOutEvent(event)
        self._touch_cursor()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._sync_cursor_blink()

    def hideEvent(self, event: QHideEvent) -> None:
        """隐藏（切换标签或视图）后停止闪烁，避免后台空转。"""
        super().hideEvent(event)
        self._sync_cursor_blink()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """左键按下时冻结渲染路径，保住点击位置设置的选区锚点。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_selecting = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """左键释放后恢复延迟渲染与自动滚动；只是单击时同样生效。"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_selecting = False
            super().mouseReleaseEvent(event)
            self._on_selection_changed()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """有选中内容时右键直接复制；没有选中时才弹出只含“全选”的菜单。"""
        if self._copy_selection():
            event.accept()
            return
        self._build_context_menu().exec(event.globalPos())

    def _copy_selection(self) -> bool:
        """复制当前选区并通知宿主；没有选区时返回 False。"""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return False
        self.copy()
        self.copied.emit(len(cursor.selectedText()))
        return True

    def _build_context_menu(self) -> QMenu:
        """构造无选中内容时的右键菜单：只提供全选。"""
        menu = QMenu(self)
        select_all_action = menu.addAction("全选")
        select_all_action.triggered.connect(self.selectAll)
        return menu

    def event(self, event: QEvent) -> bool:
        """逐键模式下让终端优先接收 Ctrl+A–Z 等应用快捷键。"""
        if (
            event.type() == QEvent.Type.ShortcutOverride
            and self._terminal_mode
            and self._input.is_raw
            and isinstance(event, QKeyEvent)
            and self._accepts_raw_shortcut(event)
        ):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """限制行缓冲编辑，或把逐键按键立即发送给设备。"""
        if not self._terminal_mode:
            super().keyPressEvent(event)
            return
        if self._input.is_raw:
            self._handle_raw_key(event)
            return
        if self._input.handle_command(event) or self._input.guard_edit(event):
            self._touch_cursor()
            return
        self._input.constrain_cursor()
        super().keyPressEvent(event)
        self._input.sync_from_document()
        self._touch_cursor()

    def _accepts_raw_shortcut(self, event: QKeyEvent) -> bool:
        """返回该 ShortcutOverride 是否应由逐键终端接管。"""
        modifiers = event.modifiers()
        if not modifiers & Qt.KeyboardModifier.ControlModifier:
            return False
        if modifiers & Qt.KeyboardModifier.AltModifier:
            return False
        key = event.key()
        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            return True
        return key in {
            Qt.Key.Key_Space,
            Qt.Key.Key_BracketLeft,
            Qt.Key.Key_Backslash,
            Qt.Key.Key_BracketRight,
            Qt.Key.Key_AsciiCircum,
            Qt.Key.Key_Underscore,
        }

    def _handle_raw_key(self, event: QKeyEvent) -> None:
        """把逐键模式的按键交给终端输入控制器。"""
        event.accept()
        key = event.key()
        if key in _MODIFIER_KEYS:
            return
        modifiers = event.modifiers()
        control = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        if control and shift and key == Qt.Key.Key_C:
            self._copy_selection()
            return
        if not self._raw_input_enabled:
            return
        if control and shift and key == Qt.Key.Key_V:
            self._prepare_raw_input()
            self.paste()
            self._touch_cursor()
            return
        self._prepare_raw_input()
        self._input.handle_command(event)
        self._touch_cursor()

    def _prepare_raw_input(self) -> None:
        """逐键输入前清理选区，把光标放回终端模型光标处。"""
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.clearSelection()
            self.setTextCursor(cursor)
        self._input.place_cursor()

    def insertFromMimeData(self, source: object) -> None:
        """粘贴单行文本；多行文本按非空行依次发送。"""
        if not self._terminal_mode:
            super().insertFromMimeData(source)
            return
        if self._input.is_raw:
            if not self._raw_input_enabled:
                return
            self._prepare_raw_input()
            self._input.insert_paste(source.text())
            self._touch_cursor()
            return
        self._input.insert_paste(source.text())

    def inputMethodEvent(self, event: QInputMethodEvent) -> None:
        """让输入法文本继续受终端输入区约束。"""
        if not self._terminal_mode:
            super().inputMethodEvent(event)
            return
        if self._input.is_raw:
            event.accept()
            commit_text = event.commitString()
            if self._raw_input_enabled and commit_text:
                self._prepare_raw_input()
                self._input.handle_raw_input_method(commit_text)
                self._touch_cursor()
            return
        self._input.constrain_cursor()
        super().inputMethodEvent(event)
        self._input.sync_from_document()
        self._touch_cursor()
