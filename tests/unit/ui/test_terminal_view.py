"""测试终端视图的切换、恢复与持久化。"""

from PySide6.QtCore import Qt
from tests.fixtures.fakes import FakeClock, FakeTransport
from tests.fixtures.ui_helpers import (
    RecordingStore,
    build_window,
    build_window_with_store,
    connect_session,
    current_tab,
)

from qserialtool.application import SessionManager
from qserialtool.domain import AppConfig, PortInfo, SerialConfig, SessionPreferences
from qserialtool.ui import MainWindow


def test_session_tab_toggles_terminal_view_and_persists_per_tab(qtbot: object) -> None:
    transport = FakeTransport()
    store = RecordingStore()
    window = build_window_with_store(qtbot, transport, store)
    tab = current_tab(window)
    splitter = tab.receive_send_splitter
    splitter.setSizes([520, 220])
    split_state = bytes(splitter.saveState().toBase64()).decode("ascii")

    qtbot.mouseClick(window.view_toggle_button, Qt.MouseButton.LeftButton)

    assert window.view_toggle_button.isChecked()
    assert window.view_toggle_button.text() == "分栏"
    assert not tab.send_panel.isVisibleTo(tab)
    assert tab.send_settings_button.isVisibleTo(tab)
    assert not tab.receive_panel.output.isReadOnly()
    assert tab.receive_panel.output.toPlainText() == ""
    assert all(
        widget.isVisibleTo(tab) == expected
        for widget, expected in (
            (tab.receive_panel.mode_combo, False),
            (tab.receive_panel.timestamp_check, False),
            (tab.receive_panel.rx_check, False),
            (tab.receive_panel.tx_check, False),
            (tab.receive_panel.terminal_timestamp_check, True),
        )
    )
    assert splitter.handleWidth() == 0
    assert not splitter.handle(1).isEnabled()
    assert tab.layout_state()[2] == split_state
    tab.receive_panel.set_terminal_draft("draft")
    assert tab.receive_panel.output.toPlainText() == "draft"

    tab.send_settings_button._format_actions["hex"].trigger()
    tab.send_settings_button._newline_actions["lf"].trigger()
    assert tab.send_panel.send_mode == "hex"
    assert tab.send_panel.line_ending == "lf"

    qtbot.mouseClick(window.view_toggle_button, Qt.MouseButton.LeftButton)

    assert not window.view_toggle_button.isChecked()
    assert window.view_toggle_button.text() == "终端"
    assert tab.send_panel.isVisibleTo(tab)
    assert not tab.send_settings_button.isVisibleTo(tab)
    assert tab.receive_panel.output.isReadOnly()
    assert tab.receive_panel.terminal_draft == "draft"
    assert "draft" not in tab.receive_panel.output.toPlainText()
    assert all(
        widget.isVisibleTo(tab) == expected
        for widget, expected in (
            (tab.receive_panel.mode_combo, True),
            (tab.receive_panel.timestamp_check, True),
            (tab.receive_panel.rx_check, True),
            (tab.receive_panel.tx_check, True),
            (tab.receive_panel.terminal_timestamp_check, False),
        )
    )
    assert splitter.handleWidth() == 6
    assert splitter.handle(1).isEnabled()
    assert bytes(splitter.saveState().toBase64()).decode("ascii") == split_state

    qtbot.mouseClick(window.view_toggle_button, Qt.MouseButton.LeftButton)
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
        terminal_timestamp=True,
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
        assert window.view_toggle_button.isChecked()
        assert window.view_toggle_button.text() == "分栏"
        assert not tab.send_panel.isVisibleTo(tab)
        assert tab.send_settings_button.isVisibleTo(tab)
        assert not tab.receive_panel.output.isReadOnly()
        assert tab.receive_panel.output.toPlainText() == ""
        assert tab.receive_panel.terminal_timestamp_check.isChecked()

        qtbot.mouseClick(window.view_toggle_button, Qt.MouseButton.LeftButton)

        assert not window.view_toggle_button.isChecked()
        assert window.view_toggle_button.text() == "终端"
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
