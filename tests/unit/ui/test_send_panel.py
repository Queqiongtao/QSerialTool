"""测试发送历史与周期发送控件。"""

from threading import Event

from PySide6.QtWidgets import QMessageBox
from tests.fixtures.fakes import FakeClock, FakeTransport

from qserialtool.application import SessionController, SessionControllerOptions
from qserialtool.domain import DEFAULT_LINE_ENDING, SerialConfig, SessionPreferences, SessionState
from qserialtool.ui import SendPanel


def _connected_controller(transport: FakeTransport) -> tuple[SessionController, Event]:
    connected = Event()

    def snapshot(value: object) -> None:
        if value.state is SessionState.CONNECTED:
            connected.set()

    controller = SessionController(
        config=SerialConfig(port="COM1"),
        transport_factory=lambda: transport,
        clock=FakeClock(),
        options=SessionControllerOptions(session_id="send-session", on_snapshot=snapshot),
    )
    controller.connect()
    assert connected.wait(1.0)
    return controller, connected


def test_send_panel_remembers_history_and_sends_periodically(qtbot: object) -> None:
    transport = FakeTransport()
    controller, _ = _connected_controller(transport)
    preferences = SessionPreferences(
        title="COM1",
        config=controller.config,
        display_mode="text",
        show_timestamp=True,
        show_rx=True,
        show_tx=True,
        autoscroll=True,
        send_history=("old",),
    )
    panel = SendPanel(controller=controller, preferences=preferences)
    qtbot.addWidget(panel)
    assert panel.line_ending == DEFAULT_LINE_ENDING

    panel.editor.setPlainText("first")
    panel.send()
    qtbot.waitUntil(lambda: transport.writes == [b"first\n"], timeout=2000)
    assert panel.history == ("old", "first")

    panel.editor.setPlainText("timer")
    panel.interval_spin.setValue(10)
    panel.periodic_button.setChecked(True)
    qtbot.waitUntil(lambda: b"timer\n" in transport.writes, timeout=2000)
    panel.periodic_button.setChecked(False)
    assert not panel.periodic_button.isChecked()

    controller.disconnect()


def test_send_panel_send_content_uses_mode_and_newline(
    qtbot: object,
    monkeypatch: object,
) -> None:
    transport = FakeTransport()
    controller, _ = _connected_controller(transport)
    panel = SendPanel(controller=controller)
    qtbot.addWidget(panel)

    assert panel.line_ending == DEFAULT_LINE_ENDING
    assert panel.send_content("")
    qtbot.waitUntil(lambda: transport.writes == [b"\n"], timeout=2000)
    assert panel.history == ()

    assert panel.send_content("ping")
    qtbot.waitUntil(lambda: transport.writes[-1] == b"ping\n", timeout=2000)
    assert panel.history == ("ping",)

    panel.set_send_mode("hex")
    panel.set_line_ending("none")
    assert panel.send_content("AA 01")
    qtbot.waitUntil(lambda: transport.writes[-1] == b"\xaa\x01", timeout=2000)
    assert panel.history == ("ping", "AA 01")

    panel.set_line_ending("none")
    writes_before = len(transport.writes)
    assert panel.send_content("")
    assert len(transport.writes) == writes_before

    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args[2]))
    assert not panel.send_content("GG")
    assert warnings
    assert panel.history == ("ping", "AA 01")

    controller.disconnect()
