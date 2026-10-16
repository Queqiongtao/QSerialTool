"""测试接收区的右键复制、菜单与选区存续。"""

from PySide6.QtCore import QPoint
from PySide6.QtGui import QContextMenuEvent, QTextCursor
from PySide6.QtWidgets import QApplication
from tests.fixtures.fakes import FakeTransport
from tests.fixtures.ui_helpers import (
    build_window,
    connect_session,
    current_tab,
    cursor_point,
    mouse_drag,
    mouse_press,
    mouse_release,
)

from qserialtool.ui import session_tab as session_tab_module
from qserialtool.ui.terminal_output import TerminalOutput


def _send_context_menu(output: TerminalOutput) -> None:
    """向接收区视口投递右键事件，走真实的 contextMenuEvent 路径。"""
    point = QPoint(5, 5)
    event = QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse,
        point,
        output.viewport().mapToGlobal(point),
    )
    QApplication.sendEvent(output.viewport(), event)


def test_receive_context_menu_offers_only_select_all_without_selection(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        output = tab.receive_panel.output
        transport.push_read(b"hello world")
        qtbot.waitUntil(lambda: "hello world" in output.toPlainText(), timeout=2000)

        split_menu = output._build_context_menu()
        assert [action.text() for action in split_menu.actions()] == ["全选"]
        split_menu.actions()[0].trigger()
        assert output.textCursor().hasSelection() is True

        tab.set_view_mode("terminal", persist=False)
        terminal_menu = output._build_context_menu()
        assert [action.text() for action in terminal_menu.actions()] == ["全选"]
    finally:
        tab.controller.close(force=True)
        window.close()


def test_receive_right_click_copies_selection_without_menu(
    qtbot: object,
    monkeypatch: object,
) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        output = tab.receive_panel.output
        transport.push_read(b"hello world")
        qtbot.waitUntil(lambda: "hello world" in output.toPlainText(), timeout=2000)

        text = output.toPlainText()
        start = text.index("hello")
        cursor = QTextCursor(output.document())
        cursor.setPosition(start)
        cursor.setPosition(start + len("hello"), QTextCursor.MoveMode.KeepAnchor)
        output.setTextCursor(cursor)

        opened: list[object] = []
        monkeypatch.setattr(output, "_build_context_menu", lambda: opened.append(object()))
        QApplication.clipboard().clear()
        _send_context_menu(output)

        assert opened == []
        assert QApplication.clipboard().text() == "hello"
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_right_click_copies_selection_without_menu(
    qtbot: object,
    monkeypatch: object,
) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output
        transport.push_read(b"hello world")
        qtbot.waitUntil(lambda: output.toPlainText() == "hello world", timeout=2000)

        cursor = QTextCursor(output.document())
        cursor.setPosition(0)
        cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        output.setTextCursor(cursor)

        opened: list[object] = []
        monkeypatch.setattr(output, "_build_context_menu", lambda: opened.append(object()))
        QApplication.clipboard().clear()
        _send_context_menu(output)

        assert opened == []
        assert QApplication.clipboard().text() == "hello"
    finally:
        tab.controller.close(force=True)
        window.close()


def test_receive_right_click_without_selection_opens_menu(
    qtbot: object,
    monkeypatch: object,
) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        output = tab.receive_panel.output
        shown: list[object] = []

        class _RecordingMenu:
            def exec(self, pos: object) -> None:
                shown.append(pos)

        monkeypatch.setattr(output, "_build_context_menu", _RecordingMenu)
        _send_context_menu(output)

        assert len(shown) == 1
    finally:
        tab.controller.close(force=True)
        window.close()


def test_right_click_copy_shows_status_hint(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        monkeypatch.setattr(session_tab_module, "_COPY_HINT_MS", 10_000)
        output = tab.receive_panel.output
        transport.push_read(b"hello world")
        qtbot.waitUntil(lambda: "hello world" in output.toPlainText(), timeout=2000)

        text = output.toPlainText()
        start = text.index("hello")
        cursor = QTextCursor(output.document())
        cursor.setPosition(start)
        cursor.setPosition(start + len("hello"), QTextCursor.MoveMode.KeepAnchor)
        output.setTextCursor(cursor)
        _send_context_menu(output)

        assert tab.status_label.text() == "已复制 5 个字符"

        # 提示期间记录刷新只更新 tooltip，不覆盖提示文本。
        transport.push_read(b"second")
        qtbot.waitUntil(lambda: len(tab.controller.records) == 2, timeout=2000)
        assert tab.status_label.text() == "已复制 5 个字符"

        # 计时结束后恢复实时状态文本。
        tab._copy_hint_timer.stop()
        tab._copy_hint_timer.timeout.emit()
        assert "已连接" in tab.status_label.text()
    finally:
        tab.controller.close(force=True)
        window.close()


def test_split_selection_survives_incoming_data(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        output = tab.receive_panel.output
        assert tab.receive_panel.autoscroll_check.isChecked() is True
        transport.push_read(b"hello world")
        qtbot.waitUntil(lambda: "hello world" in output.toPlainText(), timeout=2000)

        cursor = QTextCursor(output.document())
        cursor.setPosition(0)
        cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        output.setTextCursor(cursor)

        transport.push_read(b"second")
        qtbot.waitUntil(lambda: len(tab.controller.records) == 2, timeout=2000)

        assert output.textCursor().hasSelection() is True
        assert len(output.textCursor().selectedText()) == 5

        cleared = QTextCursor(output.document())
        cleared.setPosition(0)
        output.setTextCursor(cleared)

        assert output.textCursor().position() == output.document().characterCount() - 1
    finally:
        tab.controller.close(force=True)
        window.close()


def test_split_drag_selection_anchor_survives_incoming_data(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        output = tab.receive_panel.output
        transport.push_read(b"hello world")
        qtbot.waitUntil(lambda: "hello world" in output.toPlainText(), timeout=2000)

        text = output.toPlainText()
        start = text.index("hello")
        end = start + len("hello")

        # 按下后数据帧到达：光标不能离开点击处，否则拖选锚点会漂到文档末尾。
        mouse_press(output, cursor_point(output, start))
        transport.push_read(b"second")
        qtbot.waitUntil(lambda: "second" in output.toPlainText(), timeout=2000)

        assert output.textCursor().hasSelection() is False
        assert output.textCursor().position() == start

        mouse_drag(output, cursor_point(output, end))
        mouse_release(output, cursor_point(output, end))

        cursor = output.textCursor()
        assert cursor.selectionStart() == start
        assert cursor.selectedText() == "hello"
    finally:
        tab.controller.close(force=True)
        window.close()
