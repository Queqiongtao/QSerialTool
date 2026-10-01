"""测试发送历史与周期发送控件。"""

from threading import Event

from tests.fixtures.fakes import FakeClock, FakeTransport

from qserialtool.application import SessionController, SessionControllerOptions
from qserialtool.domain import SerialConfig, SessionPreferences, SessionState
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

    panel.editor.setPlainText("first")
    panel.send()
    qtbot.waitUntil(lambda: transport.writes == [b"first"], timeout=2000)
    assert panel.history == ("old", "first")

    panel.editor.setPlainText("timer")
    panel.interval_spin.setValue(10)
    panel.periodic_button.setChecked(True)
    qtbot.waitUntil(lambda: b"timer" in transport.writes, timeout=2000)
    panel.periodic_button.setChecked(False)
    assert not panel.periodic_button.isChecked()

    controller.disconnect()
