"""测试 JSON 配置存储与 CSV/TXT 日志输出。"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from qserialtool.domain import AppConfig, LogIOError, LogRecord, SerialConfig, SessionPreferences
from qserialtool.infrastructure import CsvLogSink, JsonConfigStore, TxtLogSink


def _record() -> LogRecord:
    return LogRecord.from_bytes(
        timestamp_utc=datetime(2026, 10, 1, 12, 0, 0, 123000, tzinfo=timezone.utc),
        direction="rx",
        raw=b"hello,world",
        encoding="utf-8",
        session_id="session-1",
    )


def _app_config() -> AppConfig:
    preferences = SessionPreferences(
        title="COM1",
        config=SerialConfig(port="COM1", baudrate=9600),
        display_mode="hex",
        show_timestamp=False,
        show_rx=False,
        show_tx=True,
        autoscroll=False,
        auto_log_enabled=True,
        auto_log_format="txt",
        auto_log_directory="/tmp/logs",
        send_history=("one", "two"),
        send_mode="hex",
        line_ending="crlf",
        periodic_interval_ms=250,
    )
    return AppConfig(
        schema_version=1,
        theme="dark",
        window_geometry="geometry",
        window_state="state",
        active_session_index=0,
        sessions=(preferences,),
        sidebar_visible=False,
        sidebar_width=360,
        content_splitter_state="splitter-state",
    )


def test_json_config_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    store = JsonConfigStore(path)

    store.save(_app_config())

    assert store.load() == _app_config()


def test_json_config_backs_up_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{broken", encoding="utf-8")
    store = JsonConfigStore(path)

    assert store.load() is None
    assert len(list(tmp_path.glob("settings.corrupt.*.json"))) == 1


def test_json_config_rejects_unknown_schema(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
    store = JsonConfigStore(path)

    assert store.load() is None
    assert list(tmp_path.glob("settings.corrupt.*.json"))


def test_csv_log_sink_writes_expected_fields(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    sink = CsvLogSink()
    sink.open(path)
    sink.write(_record())
    sink.close()

    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows == [
        {
            "timestamp": "2026-10-01T20:00:00.123+08:00",
            "direction": "RX",
            "encoding": "utf-8",
            "text": "hello,world",
            "hex": "68 65 6C 6C 6F 2C 77 6F 72 6C 64",
        }
    ]


def test_txt_log_sink_writes_readable_line(tmp_path: Path) -> None:
    path = tmp_path / "data.txt"
    sink = TxtLogSink()
    sink.open(path)
    sink.write(_record())
    sink.close()

    content = path.read_text(encoding="utf-8")
    assert "RX" in content
    assert "hello,world" in content
    assert "68 65 6C 6C 6F" in content or "hello,world" in content


def test_log_sinks_reject_write_before_open(tmp_path: Path) -> None:
    with pytest.raises(LogIOError):
        CsvLogSink().write(_record())
    with pytest.raises(LogIOError):
        TxtLogSink().write(_record())
