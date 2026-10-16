"""测试终端视图的选区在数据到达时的存续与延迟渲染。"""

from PySide6.QtGui import QTextCursor
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


def test_terminal_selection_survives_incoming_data(qtbot: object) -> None:
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

        transport.push_read(b"\r\nsecond line")
        qtbot.waitUntil(lambda: len(tab.controller.records) == 2, timeout=2000)

        assert output.textCursor().hasSelection() is True
        assert output.textCursor().selectedText() == "hello"
        assert output.toPlainText() == "hello world"

        cleared = QTextCursor(output.document())
        cleared.setPosition(0)
        output.setTextCursor(cleared)

        qtbot.waitUntil(
            lambda: output.toPlainText() == "hello world\nsecond line",
            timeout=2000,
        )
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_drag_selection_anchor_survives_incoming_data(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output
        transport.push_read(b"hello world")
        qtbot.waitUntil(lambda: output.toPlainText() == "hello world", timeout=2000)

        end = cursor_point(output, 5)
        mouse_press(output, cursor_point(output, 0))

        transport.push_read(b"\r\nsecond line")
        qtbot.waitUntil(lambda: output._renderer.deferred, timeout=2000)

        # 按住期间画面冻结：既不移动锚点，也不清掉延迟渲染标记。
        assert output.textCursor().position() == 0
        assert output.toPlainText() == "hello world"

        mouse_drag(output, end)
        mouse_release(output, end)

        cursor = output.textCursor()
        assert cursor.selectionStart() == 0
        assert cursor.selectedText() == "hello"
        assert output.toPlainText() == "hello world"
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_click_without_drag_flushes_deferred_render(qtbot: object) -> None:
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

        transport.push_read(b"\r\nsecond line")
        qtbot.waitUntil(lambda: output._renderer.deferred, timeout=2000)

        # 单击清掉选中：按下期间不补渲染，松开后才补上并恢复自动滚动。
        point = cursor_point(output, 3)
        mouse_press(output, point)
        mouse_release(output, point)

        assert output.textCursor().hasSelection() is False
        assert output.toPlainText() == "hello world\nsecond line"
        assert output.textCursor().position() == output.document().characterCount() - 1
    finally:
        tab.controller.close(force=True)
        window.close()
