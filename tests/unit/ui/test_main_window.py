"""测试主窗口、连接面板、收发面板和多标签交互。"""

from datetime import datetime, timezone

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QContextMenuEvent, QFont, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QInputDialog,
    QLineEdit,
    QMenuBar,
    QMessageBox,
    QScrollArea,
    QToolBar,
)
from tests.fixtures.fakes import FakeClock, FakeTransport

from qserialtool.application import MAX_SESSION_TITLE_LENGTH, SessionManager
from qserialtool.domain import (
    DEFAULT_LINE_ENDING,
    AppConfig,
    LogRecord,
    PortBusyError,
    PortInfo,
    SerialConfig,
    SessionPreferences,
    SessionState,
)
from qserialtool.ui import MainWindow, ReceivePanel, SessionTab, data_colors
from qserialtool.ui.terminal_output import TerminalOutput
from qserialtool.ui.theme_manager import ansi_color, highlight_colors


def _window(qtbot: object, transport: FakeTransport) -> MainWindow:
    manager = SessionManager(
        transport_factory=lambda: transport,
        clock=FakeClock(),
    )
    window = MainWindow(
        session_manager=manager,
        port_provider=lambda: (PortInfo(device="COM1"),),
    )
    qtbot.addWidget(window)
    window.show()
    return window


def _current_tab(window: MainWindow) -> SessionTab:
    tab = window.tabs.currentWidget()
    assert isinstance(tab, SessionTab)
    return tab


def _connect(qtbot: object, tab: SessionTab) -> None:
    tab.connection_panel.port_combo.setEditText("COM1")
    tab.connection_panel.baud_combo.setEditText("9600")
    qtbot.mouseClick(tab.connection_panel.connect_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            tab.controller.state is SessionState.CONNECTED
            and not tab.connection_panel.port_combo.isEnabled()
        ),
        timeout=2000,
    )


def _disconnect(qtbot: object, tab: SessionTab) -> None:
    if tab.controller.state is SessionState.CONNECTED:
        qtbot.mouseClick(tab.connection_panel.connect_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(
            lambda: tab.controller.state is SessionState.DISCONNECTED,
            timeout=2000,
        )


class _RecordingStore:
    """记录每次保存的配置，用于验证空闲状态不会重复写盘。"""

    def __init__(self) -> None:
        self.saves: list[object] = []

    def load(self) -> None:
        return None

    def save(self, config: object) -> None:
        self.saves.append(config)


def _window_with_store(
    qtbot: object,
    transport: FakeTransport,
    store: _RecordingStore,
) -> MainWindow:
    manager = SessionManager(
        transport_factory=lambda: transport,
        clock=FakeClock(),
    )
    window = MainWindow(
        session_manager=manager,
        port_provider=lambda: (PortInfo(device="COM1"), PortInfo(device="COM2")),
        config_store=store,
    )
    qtbot.addWidget(window)
    window.show()
    return window


def _window_with_ports(
    qtbot: object,
    transport: FakeTransport,
    ports: tuple[PortInfo, ...],
) -> MainWindow:
    manager = SessionManager(
        transport_factory=lambda: transport,
        clock=FakeClock(),
    )
    window = MainWindow(
        session_manager=manager,
        port_provider=lambda: ports,
    )
    qtbot.addWidget(window)
    window.show()
    return window


def test_main_window_connects_sends_receives_and_disconnects(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    try:
        _connect(qtbot, tab)
        assert tab.connection_panel.baud_combo.currentText() == "9600"
        assert not tab.connection_panel.port_combo.isEnabled()
        assert tab.send_panel.send_button.isEnabled()

        tab.send_panel.editor.setPlainText("ping")
        newline_index = tab.send_panel.newline_combo.findData("lf")
        tab.send_panel.newline_combo.setCurrentIndex(newline_index)
        qtbot.mouseClick(tab.send_panel.send_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: transport.writes == [b"ping\n"], timeout=2000)

        transport.push_read(b"pong")
        qtbot.waitUntil(lambda: "pong" in tab.receive_panel.output.toPlainText(), timeout=2000)

        hex_index = tab.receive_panel.mode_combo.findData("hex")
        tab.receive_panel.mode_combo.setCurrentIndex(hex_index)
        assert "70 6F 6E 67" in tab.receive_panel.output.toPlainText()

        _disconnect(qtbot, tab)
        assert transport.close_count == 1
    finally:
        tab.controller.close(force=True)
        window.close()


def test_main_window_creates_multiple_independent_tabs(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    first = _current_tab(window)

    second = window.new_session()

    assert window.tabs.count() == 2
    assert second.controller.session_id != first.controller.session_id
    assert second.controller.state is not SessionState.CONNECTED
    assert second.send_panel.line_ending == DEFAULT_LINE_ENDING == "lf"
    window.close()


def test_main_window_validates_invalid_baud_and_hex(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(str(args[2])),
    )

    tab.connection_panel.baud_combo.setEditText("invalid")
    qtbot.mouseClick(tab.connection_panel.connect_button, Qt.MouseButton.LeftButton)
    assert tab.controller.state is SessionState.DISCONNECTED
    assert warnings == ["波特率必须是正整数。"]

    _connect(qtbot, tab)
    hex_index = tab.send_panel.mode_combo.findData("hex")
    tab.send_panel.mode_combo.setCurrentIndex(hex_index)
    tab.send_panel.editor.setPlainText("ZZ")
    qtbot.mouseClick(tab.send_panel.send_button, Qt.MouseButton.LeftButton)
    assert warnings[-1] == "HEX 数据包含非法字符：'Z'。"

    _disconnect(qtbot, tab)
    window.close()


def test_main_window_requires_confirmation_to_close_active_tab(
    qtbot: object,
    monkeypatch: object,
) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)
    _connect(qtbot, tab)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    window._close_tab(0)

    assert window.tabs.count() == 0
    assert tab.controller.state is SessionState.CLOSED
    assert transport.close_count == 1
    window.close()


def test_receive_panel_pause_and_clear_buffer(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    try:
        _connect(qtbot, tab)
        transport.push_read(b"first")
        qtbot.waitUntil(
            lambda: "first" in tab.receive_panel.output.toPlainText(),
            timeout=2000,
        )

        qtbot.mouseClick(tab.receive_panel.pause_button, Qt.MouseButton.LeftButton)
        transport.push_read(b"second")
        qtbot.waitUntil(
            lambda: any(record.raw == b"second" for record in tab.controller.records),
            timeout=2000,
        )
        assert "second" not in tab.receive_panel.output.toPlainText()

        qtbot.mouseClick(tab.receive_panel.pause_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(
            lambda: "second" in tab.receive_panel.output.toPlainText(),
            timeout=2000,
        )
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
        )
        qtbot.mouseClick(tab.receive_panel.clear_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: tab.controller.records == (), timeout=2000)
        assert tab.receive_panel.output.toPlainText() == ""
    finally:
        tab.controller.close(force=True)
        window.close()


def test_connection_panel_allows_retry_after_open_error(
    qtbot: object,
    monkeypatch: object,
) -> None:
    transport = FakeTransport(open_error=PortBusyError("端口忙"))
    window = _window(qtbot, transport)
    tab = _current_tab(window)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    try:
        tab.connection_panel.port_combo.setEditText("COM1")
        qtbot.mouseClick(tab.connection_panel.connect_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(
            lambda: (
                tab.controller.state is SessionState.ERROR
                and tab.connection_panel.port_combo.isEnabled()
                and tab.connection_panel.connect_button.text() == "重试"
            ),
            timeout=2000,
        )
    finally:
        tab.controller.close(force=True)
        window.close()


def test_session_tab_places_settings_in_left_sidebar_and_toggles(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    assert tab.layout_splitter.widget(0) is tab.sidebar
    assert tab.layout_splitter.widget(1) is tab.main_content
    assert isinstance(tab.sidebar, QScrollArea)
    assert tab.sidebar.widget() is tab.sidebar_content
    assert tab.connection_panel.parentWidget() is tab.sidebar_content
    assert tab.log_panel.parentWidget() is tab.sidebar_content
    assert tab.sidebar_toggle_button.parentWidget() is tab.receive_panel
    assert tab.receive_send_splitter.widget(0) is tab.receive_panel
    assert tab.receive_send_splitter.widget(1) is tab.send_panel
    assert tab.sidebar.isVisible()

    qtbot.mouseClick(tab.sidebar_toggle_button, Qt.MouseButton.LeftButton)
    assert not tab.sidebar.isVisible()
    assert tab.sidebar_toggle_button.text() == "展开设置"

    qtbot.mouseClick(tab.sidebar_toggle_button, Qt.MouseButton.LeftButton)
    assert tab.sidebar.isVisible()
    assert tab.sidebar_toggle_button.text() == "收起设置"
    assert tab.layout_state()[0] is True
    window.close()


def test_session_tab_toggles_terminal_view_and_persists_per_tab(qtbot: object) -> None:
    transport = FakeTransport()
    store = _RecordingStore()
    window = _window_with_store(qtbot, transport, store)
    tab = _current_tab(window)
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
    first_window = _window(qtbot, first_transport)
    first_tab = _current_tab(first_window)
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
    tab = _current_tab(window)

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
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    try:
        _connect(qtbot, tab)
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
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    try:
        _connect(qtbot, tab)
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
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    try:
        _connect(qtbot, tab)
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
    window = _window(qtbot, transport)
    tab = _current_tab(window)
    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args[2]))

    try:
        _connect(qtbot, tab)
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
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    try:
        _connect(qtbot, tab)
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
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    try:
        _connect(qtbot, tab)
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
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    try:
        _connect(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"progress 10%\rprogress 90%")

        qtbot.waitUntil(lambda: output.toPlainText() == "progress 90%", timeout=2000)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_applies_ansi_colors_and_wide_characters(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    try:
        _connect(qtbot, tab)
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


def _fragment_formats(output: TerminalOutput) -> list[tuple[str, str]]:
    """按顺序返回文档片段的 (文本, 前景色)，用于断言渲染配色。"""
    formats: list[tuple[str, str]] = []
    block = output.document().firstBlock()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment is not None and fragment.text():
                color = fragment.charFormat().foreground().color().name()
                formats.append((fragment.text(), color))
            iterator += 1
        block = block.next()
    return formats


def test_terminal_highlights_addresses_and_links_but_keeps_ansi_colors(
    qtbot: object,
) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    try:
        _connect(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"ip 10.0.0.1 link https://a.com/x\r\n")
        transport.push_read(b"\x1b[31m10.0.0.1\x1b[0m\r\n")

        qtbot.waitUntil(lambda: output.toPlainText().count("10.0.0.1") == 2, timeout=2000)
        formats = _fragment_formats(output)
        colors = highlight_colors()

        assert ("10.0.0.1", colors.address) in formats
        assert ("https://a.com/x", colors.link) in formats
        assert ("10.0.0.1", ansi_color(1)) in formats
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_highlights_success_error_and_warning_keywords(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    try:
        _connect(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"OK ERROR WARN\r\n")

        qtbot.waitUntil(lambda: output.toPlainText().strip() == "OK ERROR WARN", timeout=2000)
        formats = _fragment_formats(output)
        colors = highlight_colors()

        assert ("OK", colors.success) in formats
        assert ("ERROR", colors.error) in formats
        assert ("WARN", colors.warning) in formats
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_highlight_toggle_disables_all_highlighting(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    try:
        _connect(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        panel = tab.receive_panel
        output = panel.output
        colors = highlight_colors()

        transport.push_read(b"OK 10.0.0.1\r\n")
        qtbot.waitUntil(lambda: output.toPlainText().strip() == "OK 10.0.0.1", timeout=2000)
        assert ("OK", colors.success) in _fragment_formats(output)
        assert ("10.0.0.1", colors.address) in _fragment_formats(output)
        assert tab.to_preferences().highlight_enabled is True

        panel.highlight_check.setChecked(False)
        qtbot.waitUntil(
            lambda: (
                not any(
                    color in {colors.success, colors.address}
                    for _, color in _fragment_formats(output)
                )
            ),
            timeout=2000,
        )
        assert tab.to_preferences().highlight_enabled is False

        panel.highlight_check.setChecked(True)
        qtbot.waitUntil(
            lambda: ("OK", colors.success) in _fragment_formats(output),
            timeout=2000,
        )
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_pause_freezes_render_but_keeps_receiving(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    try:
        _connect(qtbot, tab)
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
    window = _window(qtbot, transport)
    tab = _current_tab(window)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    try:
        _connect(qtbot, tab)
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
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    try:
        _connect(qtbot, tab)
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
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    try:
        _connect(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"themed")
        qtbot.waitUntil(lambda: output.toPlainText() == "themed", timeout=2000)

        tab.refresh_theme()

        assert output.toPlainText() == "themed"
    finally:
        tab.controller.close(force=True)
        window.close()


def test_window_minimum_size_matches_layout_target(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)

    assert window.minimumSize().width() == 900
    assert window.minimumSize().height() == 600
    window.close()


def test_data_panels_use_monospace_font(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    assert tab.receive_panel.output.font().styleHint() == QFont.StyleHint.Monospace
    assert tab.send_panel.editor.font().styleHint() == QFont.StyleHint.Monospace
    window.close()


def test_send_panel_and_content_fit_narrow_window(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    assert tab.send_panel.minimumSizeHint().width() <= 520

    window.resize(900, 600)
    qtbot.wait(50)
    receive_panel = tab.receive_panel
    for widget in (
        receive_panel.pause_button,
        receive_panel.clear_button,
        receive_panel.autoscroll_check,
        tab.view_toggle_button,
    ):
        assert widget.isVisibleTo(tab)
        assert widget.geometry().right() <= receive_panel.width()
    window.close()


def test_new_session_action_and_tab_button_create_sessions(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)

    action = next(item for item in window.main_menu.actions() if item.text() == "新建会话")
    action.trigger()
    assert window.tabs.count() == 2

    qtbot.mouseClick(window.new_tab_button, Qt.MouseButton.LeftButton)
    assert window.tabs.count() == 3
    window.close()


def test_main_window_uses_single_row_header(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)

    assert window.findChildren(QToolBar) == []
    assert window.findChildren(QMenuBar) == []

    corner = window.tabs.cornerWidget(Qt.Corner.TopRightCorner)
    assert corner is not None
    assert window.theme_combo.parentWidget() is corner
    assert window.new_tab_button.parentWidget() is corner
    assert window.menu_button.parentWidget() is corner
    assert window.theme_combo.isVisible()
    assert window.new_tab_button.isVisible()
    assert window.menu_button.isVisible()
    window.close()


def test_header_actions_keep_shortcuts_without_menu_bar(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    shortcuts = {action.text(): action.shortcut().toString() for action in window.actions()}

    assert shortcuts["新建会话"] == "Ctrl+T"
    assert shortcuts["关闭当前会话"] == "Ctrl+W"
    assert shortcuts["退出"] == "Ctrl+Q"

    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow, timeout=2000)
    qtbot.keyClick(window, Qt.Key.Key_T, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: window.tabs.count() == 2, timeout=2000)
    window.close()


def test_status_indicator_tracks_session_state(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    try:
        assert data_colors().idle in tab.state_indicator.styleSheet()
        _connect(qtbot, tab)
        assert data_colors().connected in tab.state_indicator.styleSheet()
    finally:
        _disconnect(qtbot, tab)
        window.close()


def test_status_bar_follows_port_input_while_disconnected(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    try:
        tab.connection_panel.port_combo.setEditText("COM9")
        assert "COM9" in tab.status_label.text()
    finally:
        window.close()


def test_idle_port_refresh_keeps_input_and_skips_saves(qtbot: object) -> None:
    transport = FakeTransport()
    store = _RecordingStore()
    window = _window_with_store(qtbot, transport, store)
    tab = _current_tab(window)

    try:
        qtbot.waitUntil(lambda: len(store.saves) >= 1, timeout=2000)
        qtbot.wait(700)
        editor = tab.connection_panel.port_combo.lineEdit()
        assert editor is not None
        assert tab.connection_panel.port_combo.currentText() == "COM1"
        editor.setCursorPosition(2)
        baseline = len(store.saves)

        assert tab.connection_panel._port_timer.interval() == 30_000
        for _ in range(3):
            tab.connection_panel._refresh_ports()

        assert editor.cursorPosition() == 2
        assert len(store.saves) == baseline
    finally:
        window.close()


def test_port_refresh_button_scans_immediately(qtbot: object) -> None:
    transport = FakeTransport()
    ports = ["COM1"]
    manager = SessionManager(
        transport_factory=lambda: transport,
        clock=FakeClock(),
    )
    window = MainWindow(
        session_manager=manager,
        port_provider=lambda: tuple(PortInfo(device=device) for device in ports),
    )
    qtbot.addWidget(window)
    window.show()
    tab = _current_tab(window)

    try:
        tab.connection_panel.port_combo.setEditText("COM9")
        ports.append("COM2")

        qtbot.mouseClick(tab.connection_panel.refresh_button, Qt.MouseButton.LeftButton)

        combo = tab.connection_panel.port_combo
        assert combo.findText("COM2") >= 0
        assert combo.currentText() == "COM9"
    finally:
        window.close()


def test_port_refresh_button_disabled_while_connected(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)

    try:
        assert tab.connection_panel.refresh_button.isEnabled()
        _connect(qtbot, tab)
        assert not tab.connection_panel.refresh_button.isEnabled()
        _disconnect(qtbot, tab)
        qtbot.waitUntil(tab.connection_panel.refresh_button.isEnabled, timeout=2000)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_background_tab_stops_port_refresh(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    first = _current_tab(window)

    try:
        assert first.connection_panel._port_timer.isActive()
        second = window.new_session()
        qtbot.waitUntil(
            lambda: not first.connection_panel._port_timer.isActive(),
            timeout=2000,
        )
        assert second.connection_panel._port_timer.isActive()

        window.tabs.setCurrentIndex(0)
        qtbot.waitUntil(
            first.connection_panel._port_timer.isActive,
            timeout=2000,
        )
    finally:
        window.close()


def test_port_dropdown_shows_device_description(qtbot: object) -> None:
    transport = FakeTransport()
    ports = (
        PortInfo(device="COM5", description="USB-Enhanced-SERIAL CH343"),
        PortInfo(device="COM16", description="USB-SERIAL CH340"),
    )
    window = _window_with_ports(qtbot, transport, ports)
    tab = _current_tab(window)

    try:
        combo = tab.connection_panel.port_combo
        assert combo.itemText(0) == "COM5 · USB-Enhanced-SERIAL CH343"
        assert combo.itemData(0) == "COM5"
        assert combo.currentText() == "COM5"
        assert tab.connection_panel.build_config().port == "COM5"

        combo.setCurrentIndex(1)

        assert combo.currentText() == "COM16"
        assert tab.connection_panel.current_port() == "COM16"
        assert tab.connection_panel.build_config().port == "COM16"
        assert combo.toolTip() == "COM16 · USB-SERIAL CH340"
    finally:
        window.close()


def test_status_bar_shows_device_description(qtbot: object) -> None:
    transport = FakeTransport()
    ports = (PortInfo(device="COM5", description="USB-Enhanced-SERIAL CH343"),)
    window = _window_with_ports(qtbot, transport, ports)
    tab = _current_tab(window)

    try:
        qtbot.waitUntil(
            lambda: "COM5 (USB-Enhanced-SERIAL CH343)" in tab.status_label.text(),
            timeout=2000,
        )
    finally:
        window.close()


def test_typed_port_name_stays_plain(qtbot: object) -> None:
    transport = FakeTransport()
    ports = (PortInfo(device="COM5", description="USB-Enhanced-SERIAL CH343"),)
    window = _window_with_ports(qtbot, transport, ports)
    tab = _current_tab(window)

    try:
        tab.connection_panel.port_combo.setEditText("COM9")

        assert tab.connection_panel.current_port() == "COM9"
        assert tab.connection_panel.build_config().port == "COM9"
        assert "USB-Enhanced-SERIAL CH343" not in tab.status_label.text()
        assert "COM9" in tab.status_label.text()
    finally:
        window.close()


def test_receive_panel_renders_only_recent_records(qtbot: object) -> None:
    timestamp = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
    records = tuple(
        LogRecord.from_bytes(
            timestamp_utc=timestamp,
            direction="rx",
            raw=f"line {index}".encode(),
            encoding="utf-8",
            session_id="render-cap",
        )
        for index in range(3000)
    )
    panel = ReceivePanel(
        records_provider=lambda: records,
        clear_callback=lambda: 0,
    )
    qtbot.addWidget(panel)
    panel.render_records()

    assert panel.output.document().blockCount() <= 2003
    text = panel.output.toPlainText()
    assert "已隐藏较早的 1000 条记录" in text
    assert "line 1000" in text
    assert "line 999" not in text


def test_tab_double_click_renames_session(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    store = _RecordingStore()
    window = _window_with_store(qtbot, transport, store)
    tab = _current_tab(window)
    monkeypatch.setattr(MainWindow, "_ask_session_title", lambda self, initial: "水泵")

    rect = window.tabs.tabBar().tabRect(0)
    qtbot.mouseDClick(window.tabs.tabBar(), Qt.MouseButton.LeftButton, pos=rect.center())

    try:
        assert tab.controller.title == "水泵"
        qtbot.waitUntil(lambda: window.tabs.tabText(0) == "水泵", timeout=2000)
        assert window.tabs.tabToolTip(0) == "水泵"

        window._save_timer.stop()
        window._save_config()
        assert store.saves
        assert store.saves[-1].sessions[0].title == "水泵"
    finally:
        window.close()


def test_tab_context_menu_renames_clicked_tab(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    first = _current_tab(window)
    second = window.new_session()
    monkeypatch.setattr(MainWindow, "_ask_session_title", lambda self, initial: "第二个")

    menu = window._build_tab_menu(1)
    action = next(item for item in menu.actions() if item.text() == "重命名…")
    action.trigger()

    try:
        assert second.controller.title == "第二个"
        qtbot.waitUntil(lambda: window.tabs.tabText(1) == "第二个", timeout=2000)
        assert first.controller.title == "会话 1"
        assert window.tabs.tabText(0) == "会话 1"
    finally:
        window.close()


def test_tab_rename_cancel_keeps_title(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)
    monkeypatch.setattr(MainWindow, "_ask_session_title", lambda self, initial: None)

    window._prompt_rename(0)

    try:
        assert tab.controller.title == "会话 1"
        assert window.tabs.tabText(0) == "会话 1"
    finally:
        window.close()


def test_tab_bar_context_menu_event_opens_menu(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    window.new_session()
    bar = window.tabs.tabBar()
    bar.setCurrentIndex(0)
    opened: list[tuple[int, tuple[int, int]]] = []
    monkeypatch.setattr(
        MainWindow,
        "_show_tab_menu",
        lambda self, index, global_pos: opened.append((index, global_pos.toTuple())),
    )
    position = bar.tabRect(1).center()
    global_position = bar.mapToGlobal(position)
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, position, global_position)

    handled = window.eventFilter(bar, event)

    try:
        assert handled is True
        assert window.tabs.currentIndex() == 1
        assert opened == [(1, global_position.toTuple())]
    finally:
        window.close()


def test_tab_bar_double_click_event_prompts_rename(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    window.new_session()
    bar = window.tabs.tabBar()
    prompted: list[int] = []
    monkeypatch.setattr(
        MainWindow,
        "_prompt_rename",
        lambda self, index: prompted.append(index),
    )

    def dbl_click(point: QPointF) -> QMouseEvent:
        return QMouseEvent(
            QEvent.Type.MouseButtonDblClick,
            point,
            point,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

    inside = dbl_click(QPointF(bar.tabRect(1).center()))
    outside = dbl_click(QPointF(bar.width() - 2, bar.tabRect(1).center().y()))

    try:
        assert window.eventFilter(bar, inside) is True
        assert prompted == [1]
        assert window.eventFilter(bar, outside) is False
        assert prompted == [1]
    finally:
        window.close()


def test_ask_session_title_uses_dialog_editor(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    captured: dict[str, object] = {}

    def fake_exec(dialog: QInputDialog) -> int:
        editor = dialog.findChild(QLineEdit)
        captured["editor"] = editor is not None
        if editor is not None:
            captured["max_length"] = editor.maxLength()
            captured["initial"] = editor.text()
            editor.setText("水泵控制器")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QInputDialog, "exec", fake_exec)
    result = window._ask_session_title("会话 1")

    try:
        assert result == "水泵控制器"
        assert captured.get("editor") is True
        assert captured.get("max_length") == MAX_SESSION_TITLE_LENGTH
        assert captured.get("initial") == "会话 1"
    finally:
        window.close()


def test_connection_panel_exposes_encoding_options(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    combo = _current_tab(window).connection_panel.encoding_combo

    try:
        assert [combo.itemData(index) for index in range(combo.count())] == [
            "utf-8",
            "gb18030",
            "ascii",
        ]
        assert combo.currentData() == "utf-8"
    finally:
        window.close()


def test_connection_panel_build_config_uses_selected_encoding(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)
    combo = tab.connection_panel.encoding_combo

    try:
        combo.setCurrentIndex(combo.findData("gb18030"))

        assert tab.connection_panel.build_config().encoding == "gb18030"
    finally:
        window.close()


def test_encoding_combo_locks_while_connected(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)
    tab = _current_tab(window)
    combo = tab.connection_panel.encoding_combo

    try:
        _connect(qtbot, tab)
        assert not combo.isEnabled()

        _disconnect(qtbot, tab)
        qtbot.waitUntil(combo.isEnabled, timeout=2000)
        assert combo.isEnabled()
    finally:
        tab.controller.close(force=True)
        window.close()


def test_encoding_selection_persists_and_restores(qtbot: object) -> None:
    transport = FakeTransport()
    store = _RecordingStore()
    window = _window_with_store(qtbot, transport, store)
    tab = _current_tab(window)
    combo = tab.connection_panel.encoding_combo

    try:
        combo.setCurrentIndex(combo.findData("gb18030"))
        window._save_timer.stop()
        window._save_config()

        assert store.saves[-1].sessions[0].config.encoding == "gb18030"
    finally:
        window.close()

    preferences = SessionPreferences(
        title="gb18030",
        config=SerialConfig(port="", encoding="gb18030"),
        display_mode="text",
        show_timestamp=True,
        show_rx=True,
        show_tx=True,
        autoscroll=True,
    )
    config = AppConfig(
        schema_version=1,
        theme="system",
        window_geometry=None,
        window_state=None,
        active_session_index=0,
        sessions=(preferences,),
    )
    manager = SessionManager(transport_factory=FakeTransport, clock=FakeClock())
    restored = MainWindow(
        session_manager=manager,
        port_provider=lambda: (PortInfo(device="COM1"),),
        initial_config=config,
    )
    qtbot.addWidget(restored)
    restored.show()
    restored_tab = _current_tab(restored)

    try:
        assert restored_tab.connection_panel.encoding_combo.currentData() == "gb18030"
    finally:
        restored.close()
