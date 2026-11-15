"""测试终端视图的选区在数据到达时的存续与延迟渲染。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPlainTextEdit
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

        output.clear_selection()

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


def test_terminal_mouse_release_keeps_guard_until_qt_finishes(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output
        transport.push_read(b"hello world")
        qtbot.waitUntil(lambda: output.toPlainText() == "hello world", timeout=2000)

        signals: list[tuple[bool, bool]] = []
        output.selectionChanged.connect(
            lambda: signals.append((output.textCursor().hasSelection(), output._mouse_selecting))
        )

        end = cursor_point(output, 5)
        mouse_press(output, cursor_point(output, 0))
        mouse_drag(output, end)
        mouse_release(output, end)

        assert output.textCursor().selectedText() == "hello"
        selected_states = [selecting for has_selection, selecting in signals if has_selection]
        assert selected_states
        assert all(selected_states)
        assert output._mouse_selecting is False
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_drag_selection_restores_if_qt_clears_on_release(
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

        def clear_on_release(view: QPlainTextEdit, _event: object) -> None:
            cursor = view.textCursor()
            cursor.clearSelection()
            view.setTextCursor(cursor)

        monkeypatch.setattr(QPlainTextEdit, "mouseReleaseEvent", clear_on_release)

        end = cursor_point(output, 5)
        mouse_press(output, cursor_point(output, 0))
        mouse_drag(output, end)
        mouse_release(output, end)

        assert output.textCursor().hasSelection() is True
        assert output.textCursor().selectedText() == "hello"
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_release_restores_selection_without_move_events(
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

        def clear_on_release(view: QPlainTextEdit, _event: object) -> None:
            cursor = view.textCursor()
            cursor.clearSelection()
            view.setTextCursor(cursor)

        monkeypatch.setattr(QPlainTextEdit, "mouseReleaseEvent", clear_on_release)

        mouse_press(output, cursor_point(output, 0))
        cursor = QTextCursor(output.document())
        cursor.setPosition(0)
        cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        output.setTextCursor(cursor)
        # 不发送 MouseMove，只靠按下/释放位置差识别拖选。
        mouse_release(output, cursor_point(output, 5))

        assert output.textCursor().hasSelection() is True
        assert output.textCursor().selectedText() == "hello"
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_drag_snapshot_recovers_selection_lost_before_release(
    qtbot: object,
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

        end = cursor_point(output, 5)
        mouse_press(output, cursor_point(output, 0))
        mouse_drag(output, end)

        cleared = QTextCursor(output.document())
        cleared.setPosition(0)
        output.setTextCursor(cleared)

        mouse_release(output, end)

        assert output.textCursor().hasSelection() is True
        assert output.textCursor().selectedText() == "hello"
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_place_cursor_keeps_selection(qtbot: object) -> None:
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

        output._input.place_cursor()

        assert output.textCursor().hasSelection() is True
        assert output.textCursor().selectedText() == "hello"
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_selection_lock_restores_internal_clear(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output
        transport.push_read(b"hello world")
        qtbot.waitUntil(lambda: output.toPlainText() == "hello world", timeout=2000)

        output.setFocus(Qt.FocusReason.OtherFocusReason)
        qtbot.waitUntil(output.hasFocus, timeout=2000)
        cursor = QTextCursor(output.document())
        cursor.setPosition(0)
        cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        output.setTextCursor(cursor)

        cleared = QTextCursor(output.document())
        cleared.setPosition(0)
        output.setTextCursor(cleared)

        assert output.textCursor().hasSelection() is True
        assert output.textCursor().selectedText() == "hello"
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_selection_lock_restores_without_focus(qtbot: object) -> None:
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
        output.clearFocus()
        qtbot.waitUntil(lambda: not output.hasFocus(), timeout=2000)

        cleared = QTextCursor(output.document())
        cleared.setPosition(0)
        output.setTextCursor(cleared)

        assert output.textCursor().hasSelection() is True
        assert output.textCursor().selectedText() == "hello"
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_release_restores_selection_and_scroll(
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
        for index in range(200):
            transport.push_read(f"line {index:03d} hello world\r\n".encode())
        qtbot.waitUntil(lambda: "line 199 hello world" in output.toPlainText(), timeout=3000)

        scrollbar = output.verticalScrollBar()
        scrollbar.setValue(max(0, scrollbar.maximum() // 2))
        qtbot.wait(30)
        center = output.cursorForPosition(output.viewport().rect().center()).position()
        start = max(0, center - 5)

        def clear_and_scroll(view: QPlainTextEdit, _event: object) -> None:
            cursor = view.textCursor()
            cursor.clearSelection()
            view.setTextCursor(cursor)
            view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())

        monkeypatch.setattr(QPlainTextEdit, "mouseReleaseEvent", clear_and_scroll)

        scroll_before = scrollbar.value()
        mouse_press(output, cursor_point(output, start))
        mouse_drag(output, cursor_point(output, start + 5))
        mouse_release(output, cursor_point(output, start + 5))

        assert output.textCursor().hasSelection() is True
        assert output.textCursor().selectedText()
        assert scrollbar.value() == scroll_before
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_selection_lock_released_by_typing(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output
        transport.push_read(b"hello world")
        qtbot.waitUntil(lambda: output.toPlainText() == "hello world", timeout=2000)

        output.setFocus(Qt.FocusReason.OtherFocusReason)
        qtbot.waitUntil(output.hasFocus, timeout=2000)
        cursor = QTextCursor(output.document())
        cursor.setPosition(0)
        cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        output.setTextCursor(cursor)

        QTest.keyClick(output, Qt.Key.Key_X)
        qtbot.wait(50)

        assert output.textCursor().hasSelection() is False
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_scrolled_selection_survives_streaming(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output
        for index in range(200):
            transport.push_read(f"line {index:03d} hello world\r\n".encode())
        qtbot.waitUntil(lambda: "line 199 hello world" in output.toPlainText(), timeout=3000)

        output.verticalScrollBar().setValue(0)
        cursor = QTextCursor(output.document())
        cursor.setPosition(0)
        cursor.setPosition(10, QTextCursor.MoveMode.KeepAnchor)
        output.setTextCursor(cursor)

        baseline = len(tab.controller.records)
        transport.push_read(b"new incoming line\r\n")
        qtbot.waitUntil(lambda: len(tab.controller.records) > baseline, timeout=2000)

        assert output.textCursor().hasSelection() is True
        assert output.textCursor().selectedText() == output.toPlainText()[:10]
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
