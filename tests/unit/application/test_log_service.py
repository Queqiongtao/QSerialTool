"""测试自动日志生命周期及会话集成。"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from tests.fixtures.fakes import FakeClock, FakeTransport

from qserialtool.application import (
    LogService,
    SessionController,
    SessionControllerOptions,
    default_log_directory,
)
from qserialtool.domain import LogIOError, LogRecord, SerialConfig
from qserialtool.infrastructure import TxtLogSink


def test_default_log_directory_uses_xdg_data_home_on_linux(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("qserialtool.application.log_service.sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    assert default_log_directory() == tmp_path / "QSerialTool" / "Logs"


def test_default_log_directory_falls_back_to_local_share(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("qserialtool.application.log_service.sys.platform", "linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)

    assert default_log_directory() == Path.home() / ".local" / "share" / "QSerialTool" / "Logs"


def test_default_log_directory_keeps_documents_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("qserialtool.application.log_service.sys.platform", "win32")

    assert default_log_directory() == Path.home() / "Documents" / "QSerialTool" / "Logs"


def test_log_service_creates_file_and_flushes_on_close(tmp_path: Path) -> None:
    clock = FakeClock()
    service = LogService(sink_factory=lambda _: TxtLogSink(), clock=clock)

    path = service.start(directory=str(tmp_path), port="COM:1", log_format="txt")
    record = _record()
    service.write(record)
    service.close()

    assert path.name.startswith("QSerialTool_COM_1_")
    assert "hello" in path.read_text(encoding="utf-8")


def test_log_service_rejects_invalid_configuration() -> None:
    with pytest.raises(LogIOError):
        LogService(sink_factory=lambda _: TxtLogSink(), clock=FakeClock(), flush_interval_seconds=0)
    with pytest.raises(LogIOError):
        LogService(sink_factory=lambda _: TxtLogSink(), clock=FakeClock(), flush_bytes=0)
    with pytest.raises(LogIOError):
        LogService(sink_factory=lambda _: TxtLogSink(), clock=FakeClock(), max_file_bytes=0)


def test_session_controller_writes_automatic_log(tmp_path: Path) -> None:
    transport = FakeTransport()
    controller = SessionController(
        config=SerialConfig(port="COM1"),
        transport_factory=lambda: transport,
        clock=FakeClock(),
        options=SessionControllerOptions(
            session_id="log-session",
            log_sink_factory=lambda _: TxtLogSink(),
            auto_log_enabled=True,
            auto_log_format="txt",
            auto_log_directory=str(tmp_path),
        ),
    )

    controller.connect()
    assert controller.disconnect()
    assert controller.log_path is not None
    content = controller.log_path.read_text(encoding="utf-8")
    assert "串口已连接" in content


def test_session_controller_exports_records(tmp_path: Path) -> None:
    transport = FakeTransport()
    controller = SessionController(
        config=SerialConfig(port="COM1"),
        transport_factory=lambda: transport,
        clock=FakeClock(),
        options=SessionControllerOptions(log_sink_factory=lambda _: TxtLogSink()),
    )
    controller.on_opened(controller.config)
    output = tmp_path / "export.txt"

    assert controller.export_records(output, "txt") == 1
    assert output.exists()


def _record() -> LogRecord:
    return LogRecord.from_bytes(
        timestamp_utc=datetime(2026, 10, 1, tzinfo=timezone.utc),
        direction="rx",
        raw=b"hello",
        encoding="utf-8",
        session_id="s",
    )


class RecordingSink:
    """可注入故障的日志输出替身。"""

    def __init__(
        self,
        *,
        open_error: BaseException | None = None,
        write_error: BaseException | None = None,
        flush_error: BaseException | None = None,
        close_error: BaseException | None = None,
    ) -> None:
        self.open_error = open_error
        self.write_error = write_error
        self.flush_error = flush_error
        self.close_error = close_error
        self.path: Path | None = None
        self.paths: list[Path] = []
        self.records: list[LogRecord] = []
        self.bytes_written = 0
        self.flush_count = 0
        self.close_count = 0

    def open(self, path: Path) -> None:
        if self.open_error is not None:
            raise self.open_error
        self.path = path
        self.paths.append(path)
        self.bytes_written = 0

    def write(self, record: LogRecord) -> None:
        if self.write_error is not None:
            raise self.write_error
        self.records.append(record)
        self.bytes_written += len(record.raw)

    def flush(self) -> None:
        if self.flush_error is not None:
            raise self.flush_error
        self.flush_count += 1

    def close(self) -> None:
        if self.close_error is not None:
            raise self.close_error
        self.close_count += 1


def test_log_service_avoids_filename_collisions(tmp_path: Path) -> None:
    sink = RecordingSink()
    service = LogService(sink_factory=lambda _: sink, clock=FakeClock())

    first = service.start(directory=str(tmp_path), port="COM1", log_format="csv")
    first.touch()
    service.close()
    second = service.start(directory=str(tmp_path), port="COM1", log_format="csv")

    assert first != second
    assert second.stem.endswith("_1")


def test_log_service_rotates_files_when_limit_reached(tmp_path: Path) -> None:
    sink = RecordingSink()
    service = LogService(
        sink_factory=lambda _: sink,
        clock=FakeClock(),
        max_file_bytes=5,
    )

    first = service.start(directory=str(tmp_path), port="COM1", log_format="txt")
    service.write(_record())

    assert service.path == sink.paths[1]
    assert service.path != first
    assert sink.paths[1].stem.endswith("_1")

    service.write(_record())
    assert sink.paths[2].stem.endswith("_2")
    service.close()


def test_log_service_rotates_real_txt_file(tmp_path: Path) -> None:
    service = LogService(
        sink_factory=lambda _: TxtLogSink(),
        clock=FakeClock(),
        max_file_bytes=10,
    )

    first = service.start(directory=str(tmp_path), port="COM1", log_format="txt")
    service.write(_record())

    assert service.path is not None
    assert service.path != first
    assert "hello" in first.read_text(encoding="utf-8")
    assert service.path.read_text(encoding="utf-8") == ""
    service.close()


def test_log_service_flushes_by_bytes_and_time(tmp_path: Path) -> None:
    sink = RecordingSink()
    clock = FakeClock(monotonic_value=0.0)
    service = LogService(
        sink_factory=lambda _: sink,
        clock=clock,
        flush_interval_seconds=10.0,
        flush_bytes=2,
    )
    service.start(directory=str(tmp_path), port="COM1", log_format="txt")
    service.write(_record())
    assert sink.flush_count == 1

    clock.advance(11.0)
    service.write(_record())
    assert sink.flush_count == 2
    service.close()
    assert sink.close_count == 1


def test_log_service_is_noop_without_start() -> None:
    sink = RecordingSink()
    service = LogService(sink_factory=lambda _: sink, clock=FakeClock())

    service.write(_record())
    service.flush()
    service.close()

    assert sink.records == []


def test_log_service_maps_open_failure(tmp_path: Path) -> None:
    error = LogIOError("open failed")
    sink = RecordingSink(open_error=error)
    service = LogService(sink_factory=lambda _: sink, clock=FakeClock())

    with pytest.raises(LogIOError):
        service.start(directory=str(tmp_path), port="COM1", log_format="csv")


def test_log_service_disables_sink_after_write_failure(tmp_path: Path) -> None:
    error = LogIOError("write failed")
    sink = RecordingSink(write_error=error)
    service = LogService(sink_factory=lambda _: sink, clock=FakeClock())
    service.start(directory=str(tmp_path), port="COM1", log_format="txt")

    with pytest.raises(LogIOError):
        service.write(_record())

    assert not service.is_active
    assert sink.close_count == 1


def test_log_service_reports_flush_and_close_failures(tmp_path: Path) -> None:
    flush_error = LogIOError("flush failed")
    flush_sink = RecordingSink(flush_error=flush_error)
    flush_service = LogService(sink_factory=lambda _: flush_sink, clock=FakeClock())
    flush_service.start(directory=str(tmp_path), port="COM1", log_format="txt")
    with pytest.raises(LogIOError):
        flush_service.flush()

    close_sink = RecordingSink(close_error=LogIOError("close failed"))
    close_service = LogService(sink_factory=lambda _: close_sink, clock=FakeClock())
    close_service.start(directory=str(tmp_path), port="COM2", log_format="txt")
    with pytest.raises(LogIOError):
        close_service.close()


def test_log_service_validates_factory_and_uses_default_directory(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    with pytest.raises(LogIOError):
        LogService(sink_factory=None, clock=FakeClock())  # type: ignore[arg-type]

    monkeypatch.setattr(
        "qserialtool.application.log_service.default_log_directory",
        lambda: tmp_path,
    )
    sink = RecordingSink()
    service = LogService(sink_factory=lambda _: sink, clock=FakeClock())
    path = service.start(directory="", port="", log_format="txt")
    service.close()

    assert path.parent == tmp_path
    assert path.name.startswith("QSerialTool_unknown-port_")
