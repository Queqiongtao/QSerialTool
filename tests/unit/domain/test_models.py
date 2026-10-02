"""测试领域模型默认值、验证和不可变性。"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from typing import cast

import pytest

from qserialtool.domain import (
    DEFAULT_LINE_ENDING,
    AppConfig,
    ErrorCode,
    LogRecord,
    SerialConfig,
    SessionPreferences,
    SessionSnapshot,
    SessionState,
    UserFacingError,
    ValidationError,
)


def _preferences(**overrides: object) -> SessionPreferences:
    values: dict[str, object] = {
        "title": "COM1",
        "config": SerialConfig(port="COM1"),
        "display_mode": "text",
        "show_timestamp": True,
        "show_rx": True,
        "show_tx": True,
        "autoscroll": True,
        "auto_log_enabled": False,
        "auto_log_format": "csv",
        "auto_log_directory": "",
        "send_history": (),
    }
    values.update(overrides)
    return SessionPreferences(**values)  # type: ignore[arg-type]


def test_serial_config_defaults() -> None:
    config = SerialConfig(port="COM1")

    assert config.baudrate == 115200
    assert config.bytesize == 8
    assert config.parity == "N"
    assert config.stopbits == 1.0
    assert config.flow_control == "none"
    assert config.dtr is True
    assert config.rts is True
    assert config.encoding == "utf-8"


def test_session_preferences_default_to_lf_line_ending() -> None:
    assert _preferences().line_ending == DEFAULT_LINE_ENDING == "lf"


@pytest.mark.parametrize(
    "overrides",
    [
        {"baudrate": 9600, "bytesize": 7, "parity": "E", "stopbits": 2.0},
        {"baudrate": 1, "bytesize": 5, "parity": "O", "stopbits": 1.5},
        {"bytesize": 6, "parity": "M", "flow_control": "xonxoff"},
        {"bytesize": 8, "parity": "S", "flow_control": "rtscts"},
        {"flow_control": "dsrdtr", "dtr": False, "rts": False, "encoding": "ascii"},
    ],
)
def test_serial_config_accepts_supported_values(overrides: dict[str, object]) -> None:
    SerialConfig(port="COM1", **overrides)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"port": cast(str, 1)},
        {"baudrate": 0},
        {"baudrate": True},
        {"bytesize": 9},
        {"parity": "X"},
        {"stopbits": 3.0},
        {"stopbits": True},
        {"flow_control": "software"},
        {"dtr": 1},
        {"rts": 0},
        {"encoding": "utf-16"},
    ],
)
def test_serial_config_rejects_invalid_values(overrides: dict[str, object]) -> None:
    values = {"port": "COM1", **overrides}
    with pytest.raises(ValidationError):
        SerialConfig(**values)  # type: ignore[arg-type]


def test_serial_config_allows_empty_port_until_connect() -> None:
    config = SerialConfig(port="")
    config.validate()

    with pytest.raises(ValidationError):
        config.validate_for_connect()


def test_log_record_from_bytes_derives_text_and_hex() -> None:
    timestamp = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    record = LogRecord.from_bytes(
        timestamp_utc=timestamp,
        direction="rx",
        raw="中文".encode("gb18030"),
        encoding="gb18030",
        session_id="session-1",
    )

    assert record.text == "中文"
    assert record.hex_text == "D6 D0 CE C4"
    assert record.raw == "中文".encode("gb18030")
    assert record.timestamp_utc is timestamp


@pytest.mark.parametrize(
    "overrides",
    [
        {"timestamp_utc": datetime(2026, 10, 1)},
        {"direction": "invalid"},
        {"raw": "text"},
        {"encoding": "utf-16"},
        {"session_id": ""},
        {"hex_text": "FF"},
        {"text": "wrong"},
    ],
)
def test_log_record_rejects_invalid_or_untrusted_values(overrides: dict[str, object]) -> None:
    values: dict[str, object] = {
        "timestamp_utc": datetime.now(timezone.utc),
        "direction": "rx",
        "raw": b"\x00",
        "encoding": "utf-8",
        "text": "\x00",
        "hex_text": "00",
        "session_id": "session-1",
    }
    values.update(overrides)
    with pytest.raises(ValidationError):
        LogRecord(**values)  # type: ignore[arg-type]


def test_log_record_is_immutable() -> None:
    record = LogRecord.from_bytes(
        timestamp_utc=datetime.now(timezone.utc),
        direction="tx",
        raw=b"ok",
        encoding="utf-8",
        session_id="session-1",
    )
    with pytest.raises(FrozenInstanceError):
        record.text = "changed"  # type: ignore[misc]


def test_session_snapshot_validates_counter_values() -> None:
    state = SessionState.DISCONNECTED
    config = SerialConfig(port="COM1")
    with pytest.raises(ValidationError):
        SessionSnapshot("s", "COM1", cast(SessionState, "bad"), config, None, 0, 0, 0)
    with pytest.raises(ValidationError):
        SessionSnapshot("s", "COM1", state, config, None, -1, 0, 0)


def test_session_snapshot_accepts_user_error() -> None:
    user_error = UserFacingError(ErrorCode.PORT_BUSY, "端口忙", True)
    snapshot = SessionSnapshot(
        "s",
        "COM1",
        SessionState.ERROR,
        SerialConfig(port="COM1"),
        user_error,
        1,
        2,
        3,
    )

    assert snapshot.last_error is user_error


def test_session_preferences_rejects_mutable_or_oversized_history() -> None:
    with pytest.raises(ValidationError):
        _preferences(send_history=["one"])
    with pytest.raises(ValidationError):
        _preferences(send_history=tuple(str(index) for index in range(101)))
    with pytest.raises(ValidationError):
        _preferences(send_history=(1,))


def test_session_preferences_accepts_empty_log_directory() -> None:
    preferences = _preferences()
    assert preferences.auto_log_directory == ""


def test_session_preferences_validates_view_mode() -> None:
    assert _preferences().view_mode == "split"
    assert _preferences(view_mode="terminal").view_mode == "terminal"
    with pytest.raises(ValidationError):
        _preferences(view_mode="fullscreen")


def test_app_config_validates_active_session_index() -> None:
    preferences = _preferences()
    config = AppConfig(1, "system", None, None, 0, (preferences,))
    assert config.active_session_index == 0

    with pytest.raises(ValidationError):
        AppConfig(1, "system", None, None, 1, (preferences,))
    with pytest.raises(ValidationError):
        AppConfig(1, "system", None, None, 1, ())


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema_version": 0},
        {"theme": "blue"},
        {"window_geometry": 1},
        {"window_state": 1},
        {"active_session_index": -1},
        {"sessions": []},
    ],
)
def test_app_config_rejects_invalid_values(overrides: dict[str, object]) -> None:
    values: dict[str, object] = {
        "schema_version": 1,
        "theme": "system",
        "window_geometry": None,
        "window_state": None,
        "active_session_index": 0,
        "sessions": (),
    }
    values.update(overrides)
    with pytest.raises(ValidationError):
        AppConfig(**values)  # type: ignore[arg-type]
