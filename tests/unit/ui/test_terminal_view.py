"""测试终端视图的渲染、输入与高亮。"""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import (
    QKeyEvent,
    QTextCursor,
)
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
)
from tests.fixtures.fakes import FakeClock, FakeTransport
from tests.fixtures.ui_helpers import (
    RecordingStore,
    build_window,
    build_window_with_store,
    connect_session,
    current_tab,
    cursor_point,
    fragment_formats,
    mouse_drag,
    mouse_press,
    mouse_release,
)

from qserialtool.application import SessionManager
from qserialtool.domain import (
    DEFAULT_LINE_ENDING,
    AppConfig,
    PortInfo,
    SerialConfig,
    SessionPreferences,
)
from qserialtool.ui import MainWindow
from qserialtool.ui.theme_manager import (
    ansi_color,
    highlight_colors,
)


def test_session_tab_toggles_terminal_view_and_persists_per_tab(qtbot: object) -> None:
    transport = FakeTransport()
    store = RecordingStore()
    window = build_window_with_store(qtbot, transport, store)
    tab = current_tab(window)
    splitter = tab.receive_send_splitter
    splitter.setSizes([520, 220])
    split_state = bytes(splitter.saveState().toBase64()).decode("ascii")

    qtbot.mouseClick(tab.view_toggle_button, Qt.MouseButton.LeftButton)

    assert tab.view_toggle_button.isChecked()
    assert tab.view_toggle_button.text() == "分栏"
    assert not tab.send_panel.isVisibleTo(tab)
    assert tab.send_settings_button.isVisibleTo(tab)
    assert not tab.receive_panel.output.isReadOnly()
    assert tab.receive_panel.output.toPlainText() == ""
    assert all(
        not widget.isVisibleTo(tab)
        for widget in (
            tab.receive_panel.mode_combo,
            tab.receive_panel.timestamp_check,
            tab.receive_panel.rx_check,
            tab.receive_panel.tx_check,
        )
    )
    assert splitter.handleWidth() == 0
    assert not splitter.handle(1).isEnabled()
    assert tab.layout_state()[2] == split_state
    tab.receive_panel.set_terminal_draft("draft")
    assert tab.receive_panel.output.toPlainText() == "draft"

    tab._format_actions["hex"].trigger()
    tab._newline_actions["lf"].trigger()
    assert tab.send_panel.send_mode == "hex"
    assert tab.send_panel.line_ending == "lf"

    qtbot.mouseClick(tab.view_toggle_button, Qt.MouseButton.LeftButton)

    assert not tab.view_toggle_button.isChecked()
    assert tab.view_toggle_button.text() == "终端"
    assert tab.send_panel.isVisibleTo(tab)
    assert not tab.send_settings_button.isVisibleTo(tab)
    assert tab.receive_panel.output.isReadOnly()
    assert tab.receive_panel.terminal_draft == "draft"
    assert "draft" not in tab.receive_panel.output.toPlainText()
    assert all(
        widget.isVisibleTo(tab)
        for widget in (
            tab.receive_panel.mode_combo,
            tab.receive_panel.timestamp_check,
            tab.receive_panel.rx_check,
            tab.receive_panel.tx_check,
        )
    )
    assert splitter.handleWidth() == 6
    assert splitter.handle(1).isEnabled()
    assert bytes(splitter.saveState().toBase64()).decode("ascii") == split_state

    qtbot.mouseClick(tab.view_toggle_button, Qt.MouseButton.LeftButton)
    second = window.new_session()

    assert tab.to_preferences().view_mode == "terminal"
    assert second.to_preferences().view_mode == "split"
    assert tab.receive_panel.output.toPlainText().endswith("draft")
    assert not tab.send_panel.isVisibleTo(tab)
    assert second.send_panel.isVisibleTo(second)
    assert tab.send_settings_button.isVisibleTo(tab)
    assert not second.send_settings_button.isVisibleTo(second)

    window._save_timer.stop()
    window._save_config()

    assert store.saves[-1].sessions[0].view_mode == "terminal"
    assert store.saves[-1].sessions[1].view_mode == "split"
    window.close()


def test_session_tab_restores_terminal_view_and_saved_split_state(
    qtbot: object,
) -> None:
    first_transport = FakeTransport()
    first_window = build_window(qtbot, first_transport)
    first_tab = current_tab(first_window)
    first_tab.receive_send_splitter.setSizes([520, 220])
    split_state = bytes(first_tab.receive_send_splitter.saveState().toBase64()).decode("ascii")
    first_window.close()

    manager = SessionManager(
        transport_factory=FakeTransport,
        clock=FakeClock(),
    )
    preferences = SessionPreferences(
        title="terminal",
        config=SerialConfig(port=""),
        display_mode="text",
        show_timestamp=True,
        show_rx=True,
        show_tx=True,
        autoscroll=True,
        view_mode="terminal",
    )
    config = AppConfig(
        schema_version=1,
        theme="system",
        window_geometry=None,
        window_state=None,
        active_session_index=0,
        sessions=(preferences,),
        content_splitter_state=split_state,
    )
    window = MainWindow(
        session_manager=manager,
        port_provider=lambda: (PortInfo(device="COM1"),),
        initial_config=config,
    )
    qtbot.addWidget(window)
    window.show()
    tab = current_tab(window)

    try:
        assert tab.view_toggle_button.isChecked()
        assert tab.view_toggle_button.text() == "分栏"
        assert not tab.send_panel.isVisibleTo(tab)
        assert tab.send_settings_button.isVisibleTo(tab)
        assert not tab.receive_panel.output.isReadOnly()
        assert tab.receive_panel.output.toPlainText() == ""

        qtbot.mouseClick(tab.view_toggle_button, Qt.MouseButton.LeftButton)

        assert not tab.view_toggle_button.isChecked()
        assert tab.view_toggle_button.text() == "终端"
        assert tab.send_panel.isVisibleTo(tab)
        assert tab.receive_panel.output.isReadOnly()
        restored_state = bytes(tab.receive_send_splitter.saveState().toBase64()).decode("ascii")
        assert restored_state == split_state
    finally:
        window.close()


def test_terminal_view_stops_periodic_send(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.send_panel.editor.setPlainText("timer")
        tab.send_panel.interval_spin.setValue(60_000)
        tab.send_panel.periodic_button.setChecked(True)
        assert tab.send_panel.periodic_button.isChecked()

        tab.set_view_mode("terminal", persist=False)

        assert not tab.send_panel.periodic_button.isChecked()
    finally:
        tab.controller.close(force=True)
        window.close()


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

        history_action = tab.history_menu.actions()[0]
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


def test_terminal_renders_carriage_return_overwrite(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"progress 10%\rprogress 90%")

        qtbot.waitUntil(lambda: output.toPlainText() == "progress 90%", timeout=2000)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_applies_ansi_colors_and_wide_characters(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read("\x1b[31m红\x1b[0m".encode())

        qtbot.waitUntil(lambda: output.toPlainText() == "红", timeout=2000)
        screen = tab.receive_panel._screen
        assert screen is not None
        assert screen.lines()[0][0].style.fg == 1
        assert screen.lines()[0][1].trailing is True
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_highlights_addresses_and_links_but_keeps_ansi_colors(
    qtbot: object,
) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"ip 10.0.0.1 link https://a.com/x\r\n")
        transport.push_read(b"\x1b[31m10.0.0.1\x1b[0m\r\n")

        qtbot.waitUntil(lambda: output.toPlainText().count("10.0.0.1") == 2, timeout=2000)
        formats = fragment_formats(output)
        colors = highlight_colors()

        assert ("10.0.0.1", colors.address) in formats
        assert ("https://a.com/x", colors.link) in formats
        assert ("10.0.0.1", ansi_color(1)) in formats
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_highlights_success_error_and_warning_keywords(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"OK ERROR WARN\r\n")

        qtbot.waitUntil(lambda: output.toPlainText().strip() == "OK ERROR WARN", timeout=2000)
        formats = fragment_formats(output)
        colors = highlight_colors()

        assert ("OK", colors.success) in formats
        assert ("ERROR", colors.error) in formats
        assert ("WARN", colors.warning) in formats
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_highlight_toggle_disables_all_highlighting(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        panel = tab.receive_panel
        output = panel.output
        colors = highlight_colors()

        transport.push_read(b"OK 10.0.0.1\r\n")
        qtbot.waitUntil(lambda: output.toPlainText().strip() == "OK 10.0.0.1", timeout=2000)
        assert ("OK", colors.success) in fragment_formats(output)
        assert ("10.0.0.1", colors.address) in fragment_formats(output)
        assert tab.to_preferences().highlight_enabled is True

        panel.highlight_check.setChecked(False)
        qtbot.waitUntil(
            lambda: (
                not any(
                    color in {colors.success, colors.address}
                    for _, color in fragment_formats(output)
                )
            ),
            timeout=2000,
        )
        assert tab.to_preferences().highlight_enabled is False

        panel.highlight_check.setChecked(True)
        qtbot.waitUntil(
            lambda: ("OK", colors.success) in fragment_formats(output),
            timeout=2000,
        )
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_pause_freezes_render_but_keeps_receiving(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"before")
        qtbot.waitUntil(lambda: output.toPlainText() == "before", timeout=2000)

        tab.receive_panel.pause_button.setChecked(True)
        transport.push_read(b"\rafter!")
        qtbot.waitUntil(
            lambda: (
                tab.receive_panel._screen is not None
                and tab.receive_panel._screen.text_lines()[0] == "after!"
            ),
            timeout=2000,
        )
        assert output.toPlainText() == "before"

        tab.receive_panel.pause_button.setChecked(False)
        qtbot.waitUntil(lambda: output.toPlainText() == "after!", timeout=2000)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_clear_resets_screen(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"data")
        qtbot.waitUntil(lambda: output.toPlainText() == "data", timeout=2000)

        qtbot.mouseClick(tab.receive_panel.clear_button, Qt.MouseButton.LeftButton)

        qtbot.waitUntil(lambda: output.toPlainText() == "", timeout=2000)
        assert tab.receive_panel._screen is not None
        assert tab.receive_panel._screen.text_lines() == ("",)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_rebuilds_from_buffer_after_view_round_trip(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"persisted")
        qtbot.waitUntil(lambda: output.toPlainText() == "persisted", timeout=2000)

        tab.set_view_mode("split", persist=False)
        assert tab.receive_panel._screen is None
        tab.set_view_mode("terminal", persist=False)

        assert output.toPlainText() == "persisted"
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_theme_change_redraws_without_losing_data(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"themed")
        qtbot.waitUntil(lambda: output.toPlainText() == "themed", timeout=2000)

        tab.refresh_theme()

        assert output.toPlainText() == "themed"
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
        qtbot.waitUntil(lambda: output._deferred_render, timeout=2000)

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
        qtbot.waitUntil(lambda: output._deferred_render, timeout=2000)

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
