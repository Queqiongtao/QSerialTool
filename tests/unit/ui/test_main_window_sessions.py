"""测试主窗口的会话生命周期、连接收发与标签关闭。"""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from shiboken6 import isValid
from tests.fixtures.fakes import FakeTransport
from tests.fixtures.ui_helpers import (
    build_window,
    connect_session,
    current_tab,
    disconnect_session,
)

from qserialtool.domain import DEFAULT_LINE_ENDING, SessionState


def test_main_window_connects_sends_receives_and_disconnects(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
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

        disconnect_session(qtbot, tab)
        assert transport.close_count == 1
    finally:
        tab.controller.close(force=True)
        window.close()


def test_main_window_creates_multiple_independent_tabs(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    first = current_tab(window)

    second = window.new_session()

    assert window.tabs.count() == 2
    assert second.controller.session_id != first.controller.session_id
    assert second.controller.state is not SessionState.CONNECTED
    assert second.send_panel.line_ending == DEFAULT_LINE_ENDING == "lf"
    window.close()


def test_main_window_validates_invalid_baud_and_hex(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
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

    connect_session(qtbot, tab)
    hex_index = tab.send_panel.mode_combo.findData("hex")
    tab.send_panel.mode_combo.setCurrentIndex(hex_index)
    tab.send_panel.editor.setPlainText("ZZ")
    qtbot.mouseClick(tab.send_panel.send_button, Qt.MouseButton.LeftButton)
    assert warnings[-1] == "HEX 数据包含非法字符：'Z'。"

    disconnect_session(qtbot, tab)
    window.close()


def test_main_window_requires_confirmation_to_close_active_tab(
    qtbot: object,
    monkeypatch: object,
) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    connect_session(qtbot, tab)
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


def test_close_tab_schedules_widget_destruction(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    window._close_tab(0)
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    assert window.tabs.count() == 0
    assert not isValid(tab)
    window.close()


def test_snapshot_fanout_skips_unchanged_panels(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    calls = {"connection": 0, "log": 0}
    original_connection = tab.connection_panel.apply_snapshot
    original_log = tab.log_panel.apply_snapshot

    def counting_connection(snapshot: object) -> None:
        calls["connection"] += 1
        original_connection(snapshot)

    def counting_log(snapshot: object) -> None:
        calls["log"] += 1
        original_log(snapshot)

    monkeypatch.setattr(tab.connection_panel, "apply_snapshot", counting_connection)
    monkeypatch.setattr(tab.log_panel, "apply_snapshot", counting_log)
    try:
        connect_session(qtbot, tab)
        baseline = dict(calls)
        assert baseline["connection"] > 0
        assert baseline["log"] > 0

        transport.push_read(b"payload")
        qtbot.waitUntil(lambda: "RX 7 B" in tab.status_label.text(), timeout=2000)

        assert calls == baseline

        disconnect_session(qtbot, tab)
        qtbot.waitUntil(
            lambda: calls["connection"] > baseline["connection"],
            timeout=2000,
        )
        assert calls["log"] > baseline["log"]
    finally:
        window.close()
