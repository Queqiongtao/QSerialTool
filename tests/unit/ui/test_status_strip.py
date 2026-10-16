"""测试底部状态条的连接参数、字节数单位与错误摘要显示。"""

from PySide6.QtWidgets import QWidget

from qserialtool.domain import (
    ErrorCode,
    SerialConfig,
    SessionSnapshot,
    SessionState,
    UserFacingError,
)
from qserialtool.ui.status_strip import StatusStrip, format_byte_count, format_serial_params


def test_format_byte_count_scales_units() -> None:
    assert format_byte_count(0) == "0 B"
    assert format_byte_count(1023) == "1023 B"
    assert format_byte_count(1024) == "1.0 KB"
    assert format_byte_count(1536) == "1.5 KB"
    assert format_byte_count(2 * 1024 * 1024) == "2.0 MB"
    assert format_byte_count(3 * 1024**3) == "3.0 GB"


def test_format_serial_params_summarizes_config() -> None:
    assert format_serial_params(SerialConfig(port="COM1")) == "115200 8N1"

    seven_bit = SerialConfig(port="COM1", baudrate=9600, bytesize=7, parity="E", stopbits=2.0)
    assert format_serial_params(seven_bit) == "9600 7E2"

    half_stop = SerialConfig(port="COM1", stopbits=1.5, flow_control="rtscts")
    assert format_serial_params(half_stop) == "115200 8N1.5 RTS/CTS"


def _snapshot(**overrides: object) -> SessionSnapshot:
    values: dict[str, object] = {
        "session_id": "s1",
        "title": "会话 1",
        "state": SessionState.CONNECTED,
        "config": SerialConfig(port="COM1", baudrate=9600),
        "last_error": None,
        "rx_bytes": 1536,
        "tx_bytes": 7,
        "dropped_records": 0,
    }
    values.update(overrides)
    return SessionSnapshot(**values)  # type: ignore[arg-type]


def test_status_strip_shows_params_and_units_when_connected(qtbot: object) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    strip = StatusStrip(parent)

    strip.update(snapshot=_snapshot(), port_label="COM1 · USB 转串口")

    assert strip.status_label.text() == (
        "已连接 | COM1 · USB 转串口 | 9600 8N1 | RX 1.5 KB | TX 7 B"
    )


def test_status_strip_hides_params_and_appends_error_message(qtbot: object) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    strip = StatusStrip(parent)

    strip.update(
        snapshot=_snapshot(state=SessionState.DISCONNECTED, rx_bytes=0, tx_bytes=0),
        port_label="未选择端口",
    )
    assert strip.status_label.text() == "未连接 | 未选择端口 | RX 0 B | TX 0 B"

    error = UserFacingError(ErrorCode.PORT_BUSY, "端口 COM1 已被占用。", True)
    strip.update(
        snapshot=_snapshot(state=SessionState.ERROR, last_error=error),
        port_label="COM1 · USB 转串口",
    )
    assert strip.status_label.text() == (
        "错误 | COM1 · USB 转串口 | RX 1.5 KB | TX 7 B | 错误：端口 COM1 已被占用。"
    )
