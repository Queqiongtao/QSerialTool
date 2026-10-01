"""测试 pyserial 传输包装和异常映射。"""

from collections.abc import Callable
from typing import Any, cast

import pytest
import serial

from qserialtool.domain import (
    PortBusyError,
    PortNotFoundError,
    PortPermissionError,
    SerialConfig,
    TransportIOError,
)
from qserialtool.infrastructure import SerialTransport


class FakeSerial:
    """模拟 pyserial 串口对象。"""

    def __init__(self, **settings: Any) -> None:
        self.settings = settings
        self.is_open = True
        self._dtr = True
        self._rts = True
        self.timeout = 0.0
        self.write_timeout = 0.0
        self.read_result: bytes | str = b""
        self.write_results: list[int | None] = []
        self.read_error: BaseException | None = None
        self.write_error: BaseException | None = None
        self.line_error: BaseException | None = None
        self.closed = False

    @property
    def dtr(self) -> bool:
        return self._dtr

    @dtr.setter
    def dtr(self, value: bool) -> None:
        if self.line_error is not None:
            raise self.line_error
        self._dtr = value

    @property
    def rts(self) -> bool:
        return self._rts

    @rts.setter
    def rts(self, value: bool) -> None:
        if self.line_error is not None:
            raise self.line_error
        self._rts = value

    def read(self, max_bytes: int) -> bytes | str:
        self.last_read_size = max_bytes
        if self.read_error is not None:
            raise self.read_error
        return self.read_result

    def write(self, data: bytes) -> int | None:
        self.last_write = data
        if self.write_error is not None:
            raise self.write_error
        if self.write_results:
            return self.write_results.pop(0)
        return len(data)

    def close(self) -> None:
        self.closed = True
        self.is_open = False


def _factory(serial_port: FakeSerial) -> Callable[..., serial.SerialBase]:
    def create(**settings: Any) -> serial.SerialBase:
        serial_port.settings = settings
        return cast(serial.SerialBase, serial_port)

    return create


def test_open_maps_config_and_line_state() -> None:
    fake_serial = FakeSerial()
    transport = SerialTransport(serial_factory=_factory(fake_serial))
    config = SerialConfig(port="COM3", baudrate=9600, parity="E", dtr=False, rts=False)

    transport.open(config)

    assert transport.is_open
    assert fake_serial.settings["port"] == "COM3"
    assert fake_serial.settings["baudrate"] == 9600
    assert fake_serial.settings["parity"] == "E"
    assert fake_serial.dtr is False
    assert fake_serial.rts is False


def test_open_is_idempotently_rejected_when_already_open() -> None:
    fake_serial = FakeSerial()
    transport = SerialTransport(serial_factory=_factory(fake_serial))
    transport.open(SerialConfig(port="COM3"))

    with pytest.raises(TransportIOError):
        transport.open(SerialConfig(port="COM3"))


@pytest.mark.parametrize(
    ("message", "expected_type"),
    [
        ("permission denied", PortPermissionError),
        ("Access is denied", PortBusyError),
        ("port is busy", PortBusyError),
        ("No such file or directory", PortNotFoundError),
        ("unexpected failure", TransportIOError),
    ],
)
def test_open_maps_serial_errors(message: str, expected_type: type[Exception]) -> None:
    def failing_factory(**settings: Any) -> serial.SerialBase:
        raise serial.SerialException(message)

    transport = SerialTransport(serial_factory=failing_factory)
    with pytest.raises(expected_type):
        transport.open(SerialConfig(port="COM3"))


def test_open_closes_partially_configured_port_on_line_error() -> None:
    fake_serial = FakeSerial()
    fake_serial.line_error = serial.SerialException("line failed")
    transport = SerialTransport(serial_factory=_factory(fake_serial))

    with pytest.raises(TransportIOError):
        transport.open(SerialConfig(port="COM3"))

    assert fake_serial.closed


def test_read_and_line_state_operations() -> None:
    fake_serial = FakeSerial()
    fake_serial.read_result = b"abc"
    transport = SerialTransport(serial_factory=_factory(fake_serial))
    transport.open(SerialConfig(port="COM3"))

    assert transport.read(8, timeout=0.2) == b"abc"
    assert fake_serial.last_read_size == 8
    assert fake_serial.timeout == 0.2
    transport.set_line_state(dtr=False, rts=True)
    assert fake_serial.dtr is False
    assert fake_serial.rts is True


def test_read_validates_arguments_and_result() -> None:
    fake_serial = FakeSerial()
    transport = SerialTransport(serial_factory=_factory(fake_serial))
    transport.open(SerialConfig(port="COM3"))

    with pytest.raises(TransportIOError):
        transport.read(0, timeout=0.1)
    with pytest.raises(TransportIOError):
        transport.read(1, timeout=-1)
    fake_serial.read_result = "wrong"
    with pytest.raises(TransportIOError):
        transport.read(1, timeout=0.1)


def test_read_maps_serial_error() -> None:
    fake_serial = FakeSerial()
    fake_serial.read_error = serial.SerialException("read failed")
    transport = SerialTransport(serial_factory=_factory(fake_serial))
    transport.open(SerialConfig(port="COM3"))

    with pytest.raises(TransportIOError):
        transport.read(1, timeout=0.1)


def test_write_all_handles_partial_writes() -> None:
    fake_serial = FakeSerial()
    fake_serial.write_results = [2, 3]

    transport = SerialTransport(serial_factory=_factory(fake_serial))
    transport.open(SerialConfig(port="COM3"))

    transport.write_all(b"hello", timeout=1.0)
    assert fake_serial.settings["port"] == "COM3"


def test_write_all_validates_data_timeout_and_progress() -> None:
    fake_serial = FakeSerial()
    transport = SerialTransport(serial_factory=_factory(fake_serial))
    transport.open(SerialConfig(port="COM3"))

    with pytest.raises(TransportIOError):
        transport.write_all(b"", timeout=1)
    with pytest.raises(TransportIOError):
        transport.write_all(b"data", timeout=0)
    with pytest.raises(TransportIOError):
        transport.write_all(cast(bytes, "data"), timeout=1)
    fake_serial.write_results = [0]
    with pytest.raises(TransportIOError):
        transport.write_all(b"data", timeout=1)


def test_operations_require_open_port() -> None:
    transport = SerialTransport(serial_factory=_factory(FakeSerial()))
    with pytest.raises(TransportIOError):
        transport.read(1, timeout=0.1)
    with pytest.raises(TransportIOError):
        transport.write_all(b"data", timeout=0.1)
    with pytest.raises(TransportIOError):
        transport.set_line_state(dtr=True, rts=True)


def test_close_is_idempotent_and_rejects_negative_timeout() -> None:
    fake_serial = FakeSerial()
    transport = SerialTransport(serial_factory=_factory(fake_serial))
    transport.open(SerialConfig(port="COM3"))

    transport.close(1.0)
    transport.close(1.0)
    assert fake_serial.closed
    assert not transport.is_open
    with pytest.raises(TransportIOError):
        transport.close(-1)
