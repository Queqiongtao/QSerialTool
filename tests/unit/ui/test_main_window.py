"""测试主窗口、连接面板、收发面板和多标签交互。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from tests.fixtures.fakes import FakeClock, FakeTransport

from qserialtool.application import SessionManager
from qserialtool.domain import PortBusyError, SessionState
from qserialtool.ui import MainWindow, SessionTab


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
