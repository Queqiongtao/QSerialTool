"""终端视图控件：渲染终端网格并提供光标处的内联输入。"""

from collections.abc import Callable, Sequence

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import (
    QContextMenuEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QTextCursor,
    QTextOption,
)
from PySide6.QtWidgets import QMenu, QPlainTextEdit, QWidget

from qserialtool.domain import TerminalScreen
from qserialtool.ui.terminal_inline_input import TerminalInlineInput
from qserialtool.ui.terminal_render_format import text_format
from qserialtool.ui.terminal_screen_renderer import TerminalScreenRenderer


class TerminalOutput(QPlainTextEdit):
    """渲染终端网格，并把单行输入维护为光标处的可编辑草稿。"""

    copied = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._terminal_mode = False
        self._autoscroll = True
        self._batch_update = False
        self._scrolling = False
        self._mouse_selecting = False
        self._input = TerminalInlineInput(
            self,
            after_edit=self._scroll_after_update,
            is_ready=lambda: self._renderer.has_screen,
        )
        self._renderer = TerminalScreenRenderer(
            self,
            self._input,
            after_update=self._scroll_after_update,
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
        """返回当前终端输入草稿。"""
        return self._input.draft

    def set_terminal_mode(self, enabled: bool) -> None:
        """启用或关闭终端网格渲染与内联输入。"""
        if self._terminal_mode == enabled:
            return
        self._terminal_mode = enabled
        self._renderer.reset_for_mode()
        self._input.set_enabled(enabled)
        super().clear()
        self.setReadOnly(not enabled)

    def set_submit_handler(self, handler: Callable[[str], bool]) -> None:
        """设置行提交回调；返回 False 时保留输入草稿。"""
        self._input.set_submit_handler(handler)

    def set_history_provider(self, provider: Callable[[], tuple[str, ...]]) -> None:
        """设置发送历史读取函数。"""
        self._input.set_history_provider(provider)

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
        """在草稿末尾绘制块状光标，避免污染正文内容。"""
        super().paintEvent(event)
        if not self._terminal_mode or not self._renderer.has_screen:
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
        if self.textCursor().hasSelection():
            self.copy()
            self.copied.emit(len(self.textCursor().selectedText()))
            event.accept()
            return
        self._build_context_menu().exec(event.globalPos())

    def _build_context_menu(self) -> QMenu:
        """构造无选中内容时的右键菜单：只提供全选。"""
        menu = QMenu(self)
        select_all_action = menu.addAction("全选")
        select_all_action.triggered.connect(self.selectAll)
        return menu

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """限制编辑范围，并把回车和上下键交给终端命令处理。"""
        if not self._terminal_mode:
            super().keyPressEvent(event)
            return
        if self._input.handle_command(event) or self._input.guard_edit(event):
            return
        self._input.constrain_cursor()
        super().keyPressEvent(event)
        self._input.sync_from_document()

    def insertFromMimeData(self, source: object) -> None:
        """粘贴单行文本；多行文本按非空行依次发送。"""
        if not self._terminal_mode:
            super().insertFromMimeData(source)
            return
        self._input.insert_paste(source.text())

    def inputMethodEvent(self, event: object) -> None:
        """让输入法文本继续受终端输入区约束。"""
        if not self._terminal_mode:
            super().inputMethodEvent(event)
            return
        self._input.constrain_cursor()
        super().inputMethodEvent(event)
        self._input.sync_from_document()
