"""测试终端逐键发送模式、复制粘贴与快捷键接管。"""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QInputMethodEvent, QKeyEvent, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from tests.fixtures.fakes import FakeTransport
from tests.fixtures.ui_helpers import (
    build_window,
    connect_session,
    current_tab,
    disconnect_session,
)

from qserialtool.ui import MainWindow, SessionTab


def _raw_terminal(
    qtbot: object,
    transport: FakeTransport,
) -> tuple[MainWindow, SessionTab]:
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    connect_session(qtbot, tab)
    tab.send_panel.set_line_ending("lf")
    tab.set_view_mode("terminal", persist=False)
    tab.send_settings_button._input_actions["raw"].trigger()
    output = tab.receive_panel.output
    output.setFocus()
    return window, tab


def test_raw_mode_sends_each_key_and_tab_immediately(qtbot: object) -> None:
    transport = FakeTransport()
    window, tab = _raw_terminal(qtbot, transport)

    try:
        output = tab.receive_panel.output
        assert tab.receive_panel.terminal_input_mode == "raw"

        QTest.keyClicks(output, "ls")
        qtbot.waitUntil(lambda: transport.writes == [b"l", b"s"], timeout=2000)

        QTest.keyClick(output, Qt.Key.Key_Tab)
        qtbot.waitUntil(lambda: transport.writes[-1] == b"\t", timeout=2000)

        QTest.keyClick(output, Qt.Key.Key_Return)
        qtbot.waitUntil(lambda: transport.writes[-1] == b"\n", timeout=2000)

        assert output.draft == ""
        assert output.toPlainText() == ""
    finally:
        tab.controller.close(force=True)
        window.close()


def test_raw_mode_displays_device_echo_without_local_draft(qtbot: object) -> None:
    transport = FakeTransport()
    window, tab = _raw_terminal(qtbot, transport)

    try:
        output = tab.receive_panel.output
        QTest.keyClicks(output, "l")
        qtbot.waitUntil(lambda: transport.writes == [b"l"], timeout=2000)
        assert output.toPlainText() == ""

        transport.push_read(b"l")
        qtbot.waitUntil(lambda: output.toPlainText() == "l", timeout=2000)

        QTest.keyClick(output, Qt.Key.Key_Tab)
        qtbot.waitUntil(lambda: transport.writes[-1] == b"\t", timeout=2000)

        transport.push_read(b"s")
        qtbot.waitUntil(lambda: output.toPlainText() == "ls", timeout=2000)
        assert output.draft == ""
    finally:
        tab.controller.close(force=True)
        window.close()


def test_raw_mode_maps_editing_and_navigation_keys(qtbot: object) -> None:
    transport = FakeTransport()
    window, tab = _raw_terminal(qtbot, transport)

    try:
        output = tab.receive_panel.output
        QTest.keyClick(output, Qt.Key.Key_Backspace)
        QTest.keyClick(output, Qt.Key.Key_Up)
        QTest.keyClick(output, Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(output, Qt.Key.Key_Home)
        QTest.keyClick(output, Qt.Key.Key_Delete)

        expected = [b"\x7f", b"\x1b[A", b"\x1b[1;5D", b"\x1b[H", b"\x1b[3~"]
        qtbot.waitUntil(lambda: transport.writes == expected, timeout=3000)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_raw_mode_passes_control_letters_to_device(qtbot: object) -> None:
    transport = FakeTransport()
    window, tab = _raw_terminal(qtbot, transport)

    try:
        output = tab.receive_panel.output
        for key in (Qt.Key.Key_A, Qt.Key.Key_C, Qt.Key.Key_D, Qt.Key.Key_R, Qt.Key.Key_Z):
            QTest.keyClick(output, key, Qt.KeyboardModifier.ControlModifier)

        expected = [b"\x01", b"\x03", b"\x04", b"\x12", b"\x1a"]
        qtbot.waitUntil(lambda: transport.writes == expected, timeout=3000)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_raw_mode_copy_paste_shortcuts(qtbot: object) -> None:
    transport = FakeTransport()
    window, tab = _raw_terminal(qtbot, transport)

    try:
        output = tab.receive_panel.output
        transport.push_read(b"hello world")
        qtbot.waitUntil(lambda: output.toPlainText() == "hello world", timeout=2000)

        cursor = output.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        output.setTextCursor(cursor)
        QTest.keyClick(
            output,
            Qt.Key.Key_C,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
        assert QApplication.clipboard().text() == "hello"
        assert transport.writes == []

        QApplication.clipboard().setText("pasted")
        QTest.keyClick(
            output,
            Qt.Key.Key_V,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
        qtbot.waitUntil(lambda: transport.writes == [b"pasted"], timeout=2000)

        QTest.keyClick(output, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
        qtbot.waitUntil(lambda: transport.writes[-1] == b"\x16", timeout=2000)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_raw_mode_ctrl_insert_copies_without_sending(qtbot: object) -> None:
    transport = FakeTransport()
    window, tab = _raw_terminal(qtbot, transport)

    try:
        output = tab.receive_panel.output
        transport.push_read(b"hello")
        qtbot.waitUntil(lambda: output.toPlainText() == "hello", timeout=2000)

        cursor = output.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        output.setTextCursor(cursor)
        QApplication.clipboard().clear()

        QTest.keyClick(output, Qt.Key.Key_Insert, Qt.KeyboardModifier.ControlModifier)

        assert QApplication.clipboard().text() == "hello"
        assert transport.writes == []
        assert output.textCursor().hasSelection() is True
    finally:
        tab.controller.close(force=True)
        window.close()


def test_raw_mode_shift_insert_pastes_clipboard(qtbot: object) -> None:
    transport = FakeTransport()
    window, tab = _raw_terminal(qtbot, transport)

    try:
        output = tab.receive_panel.output
        output.setFocus()
        QApplication.clipboard().setText("pasted")

        QTest.keyClick(output, Qt.Key.Key_Insert, Qt.KeyboardModifier.ShiftModifier)

        qtbot.waitUntil(lambda: transport.writes == [b"pasted"], timeout=2000)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_raw_mode_ctrl_c_interrupts_even_with_selection(qtbot: object) -> None:
    transport = FakeTransport()
    window, tab = _raw_terminal(qtbot, transport)

    try:
        output = tab.receive_panel.output
        transport.push_read(b"hello")
        qtbot.waitUntil(lambda: output.toPlainText() == "hello", timeout=2000)

        cursor = output.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
        output.setTextCursor(cursor)
        QTest.keyClick(output, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)

        qtbot.waitUntil(lambda: transport.writes == [b"\x03"], timeout=2000)
        assert not output.textCursor().hasSelection()
    finally:
        tab.controller.close(force=True)
        window.close()


def test_raw_mode_paste_multiline_and_ime_commit(qtbot: object) -> None:
    transport = FakeTransport()
    window, tab = _raw_terminal(qtbot, transport)

    try:
        output = tab.receive_panel.output
        QApplication.clipboard().setText("one\r\ntwo")
        QTest.keyClick(
            output,
            Qt.Key.Key_V,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        )
        qtbot.waitUntil(lambda: transport.writes == [b"one\n", b"two\n"], timeout=3000)

        event = QInputMethodEvent()
        event.setCommitString("中")
        QApplication.sendEvent(output, event)
        qtbot.waitUntil(lambda: transport.writes[-1] == "中".encode(), timeout=2000)
        assert output.draft == ""
    finally:
        tab.controller.close(force=True)
        window.close()


def test_raw_mode_ignores_keys_when_disconnected(
    qtbot: object,
    monkeypatch: object,
) -> None:
    transport = FakeTransport()
    window, tab = _raw_terminal(qtbot, transport)
    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args[2]))

    try:
        output = tab.receive_panel.output
        disconnect_session(qtbot, tab)
        before = list(transport.writes)

        QTest.keyClicks(output, "x")
        QTest.keyClick(output, Qt.Key.Key_Tab)
        qtbot.wait(50)

        assert transport.writes == before
        assert warnings == []
    finally:
        window.close()


def test_raw_mode_shortcut_override_takes_ctrl_letters(qtbot: object) -> None:
    transport = FakeTransport()
    window, tab = _raw_terminal(qtbot, transport)

    try:
        output = tab.receive_panel.output
        for key in (Qt.Key.Key_T, Qt.Key.Key_W, Qt.Key.Key_L, Qt.Key.Key_Q):
            raw_event = QKeyEvent(
                QEvent.Type.ShortcutOverride,
                key,
                Qt.KeyboardModifier.ControlModifier,
            )
            QApplication.sendEvent(output, raw_event)
            assert raw_event.isAccepted()

        tab._set_terminal_input_mode("line")
        raw_event = QKeyEvent(
            QEvent.Type.ShortcutOverride,
            Qt.Key.Key_T,
            Qt.KeyboardModifier.ControlModifier,
        )
        QApplication.sendEvent(output, raw_event)
        assert not raw_event.isAccepted()
    finally:
        tab.controller.close(force=True)
        window.close()


def test_switching_between_line_and_raw_discards_local_draft(qtbot: object) -> None:
    transport = FakeTransport()
    window, tab = _raw_terminal(qtbot, transport)

    try:
        output = tab.receive_panel.output
        tab._set_terminal_input_mode("line")
        QTest.keyClicks(output, "abc")
        assert output.draft == "abc"
        assert transport.writes == []

        tab._set_terminal_input_mode("raw")
        assert output.draft == ""
        assert output.toPlainText() == ""
        assert transport.writes == []

        QTest.keyClick(output, Qt.Key.Key_X)
        qtbot.waitUntil(lambda: transport.writes == [b"x"], timeout=2000)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_raw_mode_ignores_hex_format_and_sends_text(
    qtbot: object,
    monkeypatch: object,
) -> None:
    transport = FakeTransport()
    window, tab = _raw_terminal(qtbot, transport)
    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args[2]))

    try:
        tab.send_panel.set_send_mode("hex")
        output = tab.receive_panel.output
        output.setFocus()

        QTest.keyClick(output, Qt.Key.Key_A)

        qtbot.waitUntil(lambda: transport.writes == [b"a"], timeout=2000)
        assert warnings == []
        assert tab.send_panel.send_mode == "hex"
    finally:
        tab.controller.close(force=True)
        window.close()


def test_raw_mode_history_menu_sends_selected_line(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.send_panel.set_line_ending("lf")
        tab.set_view_mode("terminal", persist=False)
        tab.receive_panel.set_terminal_input_mode("line")
        output = tab.receive_panel.output
        output.setFocus()

        QTest.keyClicks(output, "first")
        QTest.keyClick(output, Qt.Key.Key_Return)
        qtbot.waitUntil(lambda: transport.writes == [b"first\n"], timeout=2000)

        tab.send_settings_button._input_actions["raw"].trigger()
        history_action = tab.send_settings_button.history_menu.actions()[0]
        history_action.trigger()
        qtbot.waitUntil(lambda: transport.writes[-1] == b"first\n", timeout=2000)
        assert output.draft == ""
    finally:
        tab.controller.close(force=True)
        window.close()
