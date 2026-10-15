"""测试连接面板的端口刷新、编码选项与状态栏联动。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMessageBox,
)
from tests.fixtures.fakes import FakeClock, FakeTransport
from tests.fixtures.ui_helpers import (
    RecordingStore,
    build_window,
    build_window_with_ports,
    build_window_with_store,
    connect_session,
    current_tab,
    disconnect_session,
)

from qserialtool.application import SessionManager
from qserialtool.domain import (
    AppConfig,
    PortBusyError,
    PortInfo,
    SerialConfig,
    SessionPreferences,
    SessionState,
)
from qserialtool.ui import MainWindow


def test_connection_panel_allows_retry_after_open_error(
    qtbot: object,
    monkeypatch: object,
) -> None:
    transport = FakeTransport(open_error=PortBusyError("端口忙"))
    window = build_window(qtbot, transport)
    tab = current_tab(window)
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


def test_status_bar_follows_port_input_while_disconnected(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        tab.connection_panel.port_combo.setEditText("COM9")
        assert "COM9" in tab.status_label.text()
    finally:
        window.close()


def test_idle_port_refresh_keeps_input_and_skips_saves(qtbot: object) -> None:
    transport = FakeTransport()
    store = RecordingStore()
    window = build_window_with_store(qtbot, transport, store)
    tab = current_tab(window)

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
    tab = current_tab(window)

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
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        assert tab.connection_panel.refresh_button.isEnabled()
        connect_session(qtbot, tab)
        assert not tab.connection_panel.refresh_button.isEnabled()
        disconnect_session(qtbot, tab)
        qtbot.waitUntil(tab.connection_panel.refresh_button.isEnabled, timeout=2000)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_background_tab_stops_port_refresh(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    first = current_tab(window)

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
    window = build_window_with_ports(qtbot, transport, ports)
    tab = current_tab(window)

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
    window = build_window_with_ports(qtbot, transport, ports)
    tab = current_tab(window)

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
    window = build_window_with_ports(qtbot, transport, ports)
    tab = current_tab(window)

    try:
        tab.connection_panel.port_combo.setEditText("COM9")

        assert tab.connection_panel.current_port() == "COM9"
        assert tab.connection_panel.build_config().port == "COM9"
        assert "USB-Enhanced-SERIAL CH343" not in tab.status_label.text()
        assert "COM9" in tab.status_label.text()
    finally:
        window.close()


def test_connection_panel_exposes_encoding_options(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    combo = current_tab(window).connection_panel.encoding_combo

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
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    combo = tab.connection_panel.encoding_combo

    try:
        combo.setCurrentIndex(combo.findData("gb18030"))

        assert tab.connection_panel.build_config().encoding == "gb18030"
    finally:
        window.close()


def test_encoding_combo_locks_while_connected(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    combo = tab.connection_panel.encoding_combo

    try:
        connect_session(qtbot, tab)
        assert not combo.isEnabled()

        disconnect_session(qtbot, tab)
        qtbot.waitUntil(combo.isEnabled, timeout=2000)
        assert combo.isEnabled()
    finally:
        tab.controller.close(force=True)
        window.close()


def test_encoding_selection_persists_and_restores(qtbot: object) -> None:
    transport = FakeTransport()
    store = RecordingStore()
    window = build_window_with_store(qtbot, transport, store)
    tab = current_tab(window)
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
    restored_tab = current_tab(restored)

    try:
        assert restored_tab.connection_panel.encoding_combo.currentData() == "gb18030"
    finally:
        restored.close()
