"""使用 pyserial loop:// 验证无界面串口链路。"""

from threading import Condition

import serial

from qserialtool.application import SessionController, SessionControllerOptions
from qserialtool.domain import SerialConfig, SessionState
from qserialtool.infrastructure import SerialTransport, SystemClock


def _loop_factory(**settings: object) -> serial.SerialBase:
    url = str(settings.pop("port"))
    return serial.serial_for_url(url, **settings)


class EventRecorder:
    def __init__(self) -> None:
        self.condition = Condition()
        self.snapshots = []
        self.records = []

    def snapshot(self, value: object) -> None:
        with self.condition:
            self.snapshots.append(value)
            self.condition.notify_all()

    def record(self, value: object) -> None:
        with self.condition:
            self.records.append(value)
            self.condition.notify_all()

    def wait_for(self, predicate: object, timeout: float = 2.0) -> bool:
        with self.condition:
            return self.condition.wait_for(
                lambda: (
                    any(predicate(snapshot) for snapshot in self.snapshots)
                    or any(predicate(record) for record in self.records)
                ),
                timeout,
            )


def test_loopback_session_sends_and_receives_bytes() -> None:
    events = EventRecorder()
    controller = SessionController(
        config=SerialConfig(port="loop://"),
        transport_factory=lambda: SerialTransport(serial_factory=_loop_factory),
        clock=SystemClock(),
        options=SessionControllerOptions(
            session_id="loop-session",
            title="Loopback",
            on_snapshot=events.snapshot,
            on_record=events.record,
        ),
    )

    try:
        controller.connect()
        assert events.wait_for(lambda item: getattr(item, "state", None) is SessionState.CONNECTED)

        controller.send(b"ping")
        assert events.wait_for(
            lambda item: (
                getattr(item, "direction", None) == "rx" and getattr(item, "raw", None) == b"ping"
            )
        )
    finally:
        controller.close(force=True)
