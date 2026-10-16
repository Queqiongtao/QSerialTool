"""测试单会话控制器的收发数据流、缓冲与自动日志。"""

from pathlib import Path

from tests.fixtures.fakes import (
    FakeClock,
    FakeTransport,
    RecordRecorder,
    SnapshotRecorder,
    build_controller,
)

from qserialtool.application import SessionController, SessionControllerOptions
from qserialtool.domain import LogIOError, SerialConfig, SessionState


def test_controller_connects_sends_receives_and_disconnects() -> None:
    transport = FakeTransport()
    snapshots = SnapshotRecorder()
    records = RecordRecorder()
    controller = build_controller(transport, snapshots=snapshots, records=records)

    assert controller.state is SessionState.DISCONNECTED
    controller.connect()
    assert snapshots.wait_for(lambda snapshot: snapshot.state is SessionState.CONNECTED)

    controller.send(b"tx")
    assert transport.write_event.wait(1.0)
    assert snapshots.wait_for(lambda snapshot: snapshot.tx_bytes == 2)

    transport.push_read(b"rx")
    assert records.wait_for(lambda record: record.direction == "rx" and record.raw == b"rx")
    assert snapshots.wait_for(lambda snapshot: snapshot.rx_bytes == 2)

    assert controller.disconnect()
    assert controller.state is SessionState.DISCONNECTED
    assert transport.close_count == 1


def test_controller_joins_split_multibyte_characters_across_reads() -> None:
    transport = FakeTransport()
    snapshots = SnapshotRecorder()
    records = RecordRecorder()
    controller = build_controller(transport, snapshots=snapshots, records=records)
    controller.connect()
    assert snapshots.wait_for(lambda snapshot: snapshot.state is SessionState.CONNECTED)

    data = "串口".encode()
    transport.push_read(data[:2])
    transport.push_read(data[2:])

    assert records.wait_for(lambda record: record.direction == "rx" and record.text == "串口")
    record = next(item for item in records.records if item.direction == "rx")
    assert record.raw == data
    assert record.hex_text == "E4 B8 B2 E5 8F A3"
    assert snapshots.wait_for(lambda snapshot: snapshot.rx_bytes == len(data))
    assert controller.disconnect()


def test_controller_flush_reports_incomplete_tail_on_disconnect() -> None:
    transport = FakeTransport()
    snapshots = SnapshotRecorder()
    records = RecordRecorder()
    controller = build_controller(transport, snapshots=snapshots, records=records)
    controller.connect()
    assert snapshots.wait_for(lambda snapshot: snapshot.state is SessionState.CONNECTED)

    transport.push_read(b"A\xe4")
    assert records.wait_for(lambda record: record.direction == "rx" and record.raw == b"A")

    assert controller.disconnect()

    tail = [item for item in records.records if item.direction == "rx"][-1]
    assert tail.raw == b"\xe4"
    assert tail.text == "<E4>"
    assert controller.snapshot.rx_bytes == 2


class _FailingLogSink:
    """写入即失败的日志输出，用于验证自动日志故障的上报与诊断记录。"""

    def open(self, path: object) -> None:
        return None

    def write(self, record: object) -> None:
        raise LogIOError("磁盘已满")

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


def test_controller_reports_automatic_log_failures_once(caplog: object, tmp_path: Path) -> None:
    transport = FakeTransport()
    snapshots = SnapshotRecorder()
    controller = SessionController(
        config=SerialConfig(port="COM1"),
        transport_factory=lambda: transport,
        clock=FakeClock(),
        options=SessionControllerOptions(
            session_id="log-failure",
            on_snapshot=snapshots,
            log_sink_factory=lambda _format: _FailingLogSink(),
            auto_log_enabled=True,
            auto_log_directory=str(tmp_path),
        ),
    )

    try:
        controller.connect()
        assert snapshots.wait_for(lambda snapshot: snapshot.state is SessionState.CONNECTED)

        transport.push_read(b"data")

        assert snapshots.wait_for(lambda snapshot: snapshot.last_error is not None)
        assert controller.snapshot.last_error is not None
        assert "自动日志写入失败：磁盘已满" in caplog.text
    finally:
        controller.close(force=True)


def test_controller_clear_buffer_keeps_counters() -> None:
    transport = FakeTransport()
    snapshots = SnapshotRecorder()
    controller = build_controller(transport, snapshots=snapshots)
    controller.connect()
    assert snapshots.wait_for(lambda snapshot: snapshot.state is SessionState.CONNECTED)

    removed = controller.clear_buffer()

    assert removed == 1
    assert controller.records == ()
    assert controller.snapshot.rx_bytes == 0
    assert controller.disconnect()
