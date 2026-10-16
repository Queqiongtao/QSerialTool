"""测试终端视图的内联输入、历史、粘贴与编辑约束。"""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from tests.fixtures.fakes import FakeTransport
from tests.fixtures.ui_helpers import build_window, connect_session, current_tab

from qserialtool.domain import DEFAULT_LINE_ENDING


def test_terminal_inline_input_sends_lines_and_recalls_history(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        assert tab.send_panel.line_ending == DEFAULT_LINE_ENDING
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output
        output.setFocus()

        QTest.keyClicks(output, "first")
        QTest.keyClick(output, Qt.Key.Key_Return)
        qtbot.waitUntil(lambda: transport.writes == [b"first\n"], timeout=2000)
        assert output.toPlainText() == ""

        QTest.keyClicks(output, "second")
        QTest.keyClick(output, Qt.Key.Key_Return)
        qtbot.waitUntil(lambda: transport.writes[-1] == b"second\n", timeout=2000)
        assert output.toPlainText() == ""

        QTest.keyClick(output, Qt.Key.Key_Up)
        assert output.draft == "second"
        QTest.keyClick(output, Qt.Key.Key_Up)
        assert output.draft == "first"
        QTest.keyClick(output, Qt.Key.Key_Down)
        assert output.draft == "second"
        QTest.keyClick(output, Qt.Key.Key_Down)
        assert output.draft == ""

        history_action = tab.send_settings_button.history_menu.actions()[0]
        assert history_action.text() == "second"
        history_action.trigger()
        assert output.draft == "second"
        assert transport.writes[-1] == b"second\n"
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_input_continues_after_received_device_prompt(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output
        output.setFocus()

        transport.push_read(b"#")
        qtbot.waitUntil(lambda: output.toPlainText() == "#", timeout=2000)

        QTest.keyClicks(output, "cmd")
        assert output.toPlainText() == "#cmd"

        QTest.keyClick(output, Qt.Key.Key_Return)
        qtbot.waitUntil(lambda: transport.writes == [b"cmd\n"], timeout=2000)
        assert output.toPlainText() == "#"

        transport.push_read(b"cmd\r\n#")
        qtbot.waitUntil(lambda: output.toPlainText() == "#cmd\n#", timeout=2000)

        QTest.keyClicks(output, "next")
        assert output.toPlainText() == "#cmd\n#next"
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_empty_enter_without_newline_is_noop(
    qtbot: object,
    monkeypatch: object,
) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args[2]))

    try:
        connect_session(qtbot, tab)
        tab.send_panel.set_line_ending("none")
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output
        output.setFocus()

        QTest.keyClick(output, Qt.Key.Key_Return)

        assert transport.writes == []
        assert warnings == []
        assert output.draft == ""
        assert output.toPlainText() == ""

        tab.send_panel.set_line_ending("lf")
        QTest.keyClick(output, Qt.Key.Key_Return)

        qtbot.waitUntil(lambda: transport.writes == [b"\n"], timeout=2000)
        assert warnings == []
        assert output.draft == ""
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_paste_sends_non_empty_lines(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.send_panel.set_line_ending("lf")
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output
        output.setFocus()
        QApplication.clipboard().setText("one\r\ntwo\n\nthree")

        QTest.keyClick(output, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)

        qtbot.waitUntil(
            lambda: transport.writes == [b"one\n", b"two\n", b"three\n"],
            timeout=3000,
        )
        assert output.draft == ""
        assert output.toPlainText() == ""
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_invalid_hex_keeps_draft(
    qtbot: object,
    monkeypatch: object,
) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.send_panel.set_send_mode("hex")
        tab.send_panel.set_line_ending("lf")
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output
        warnings: list[str] = []
        monkeypatch.setattr(
            QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args[2])
        )
        output.setFocus()

        QTest.keyClicks(output, "GG")
        QTest.keyClick(output, Qt.Key.Key_Return)

        assert output.draft == "GG"
        assert output.toPlainText() == "GG"
        assert transport.writes == []
        assert warnings
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_receive_text_cannot_be_edited(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output
        output.setFocus()
        transport.push_read(b"hello world")
        qtbot.waitUntil(lambda: output.toPlainText() == "hello world", timeout=2000)

        QTest.keyClicks(output, "x")
        assert output.draft == "x"
        QTest.keyClick(output, Qt.Key.Key_Escape)
        assert output.draft == ""

        cursor = output.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        output.setTextCursor(cursor)

        QTest.keyClick(output, Qt.Key.Key_Delete)
        assert output.toPlainText() == "hello world"
        QTest.keyClick(output, Qt.Key.Key_Backspace)
        assert output.toPlainText() == "hello world"
        QTest.keyClick(output, Qt.Key.Key_X, Qt.KeyboardModifier.ControlModifier)
        assert output.toPlainText() == "hello world"

        QApplication.clipboard().clear()
        cursor.setPosition(0)
        cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        output.setTextCursor(cursor)
        QApplication.sendEvent(
            output,
            QKeyEvent(
                QEvent.Type.KeyPress,
                Qt.Key.Key_C,
                Qt.KeyboardModifier.ControlModifier,
                "c",
            ),
        )
        assert QApplication.clipboard().text() == "hello"
        assert output.toPlainText() == "hello world"
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_paste_lands_in_draft_not_log_text(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output
        output.setFocus()
        transport.push_read(b"hello world")
        qtbot.waitUntil(lambda: output.toPlainText() == "hello world", timeout=2000)

        QApplication.clipboard().setText("pasted")
        cursor = output.textCursor()
        cursor.setPosition(3)
        output.setTextCursor(cursor)
        qtbot.keyClick(output, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)

        assert output.toPlainText() == "hello worldpasted"
    finally:
        tab.controller.close(force=True)
        window.close()
