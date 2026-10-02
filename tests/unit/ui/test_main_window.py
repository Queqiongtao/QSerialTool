"""测试主窗口、连接面板、收发面板和多标签交互。"""

from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QMenuBar, QMessageBox, QScrollArea, QToolBar
from tests.fixtures.fakes import FakeClock, FakeTransport

from qserialtool.application import SessionManager
from qserialtool.domain import LogRecord, PortBusyError, SessionState
from qserialtool.ui import MainWindow, ReceivePanel, SessionTab, data_colors


def _window(qtbot: object, transport: FakeTransport) -> MainWindow:
    manager = SessionManager(
        transport_factory=lambda: transport,
        clock=FakeClock(),
    )
    window = MainWindow(
        session_manager=manager,
        port_provider=lambda: ("COM1",),
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
        port_provider=lambda: ("COM1", "COM2"),
        config_store=store,
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


def test_window_minimum_size_matches_layout_target(qtbot: object) -> None:
    transport = FakeTransport()
    window = _window(qtbot, transport)

    assert window.minimumSize().width() == 900
    assert window.minimumSize().height() == 600
    assert window.minimumSizeHint().width() <= 900
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
    assert tab.main_content.minimumSizeHint().width() <= 620
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
        port_provider=lambda: tuple(ports),
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

    assert panel.output.document().blockCount() <= 2002
    text = panel.output.toPlainText()
    assert "已隐藏较早的 1000 条记录" in text
    assert "line 1000" in text
    assert "line 999" not in text
