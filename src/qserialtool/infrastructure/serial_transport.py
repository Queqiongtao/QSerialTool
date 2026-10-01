"""pyserial 传输实现和异常映射。"""

from collections.abc import Callable
from contextlib import suppress
from time import monotonic

import serial

from qserialtool.domain import (
    DomainError,
    PortBusyError,
    PortNotFoundError,
    PortPermissionError,
    SerialConfig,
    TransportIOError,
)

SerialFactory = Callable[..., serial.SerialBase]
MonotonicFunction = Callable[[], float]


def _map_serial_error(error: BaseException) -> DomainError:
    message = str(error).strip()
    normalized = message.lower()
    if "permission denied" in normalized or "errno 13" in normalized:
        return PortPermissionError(message or "当前用户没有串口权限。")
    if (
        "access is denied" in normalized
        or "busy" in normalized
        or "in use" in normalized
        or "cannot lock" in normalized
    ):
        return PortBusyError(message or "串口正被占用。")
    if (
        "file not found" in normalized
        or "no such file" in normalized
        or "could not find" in normalized
    ):
        return PortNotFoundError(message or "串口不存在。")
    return TransportIOError(message or "串口操作失败。")


class SerialTransport:
    """使用 pyserial 执行独占串口读写。"""

    def __init__(
        self,
        serial_factory: SerialFactory = serial.Serial,
        monotonic_function: MonotonicFunction = monotonic,
    ) -> None:
        self._serial_factory = serial_factory
        self._monotonic = monotonic_function
        self._serial: serial.SerialBase | None = None

    def open(self, config: SerialConfig) -> None:
        """打开串口并应用流控和 DTR/RTS 状态。"""
        config.validate_for_connect()
        if self._serial is not None and self.is_open:
            raise TransportIOError("串口已经打开。")
        settings = {
            "port": config.port,
            "baudrate": config.baudrate,
            "bytesize": config.bytesize,
            "parity": config.parity,
            "stopbits": config.stopbits,
            "timeout": 0.05,
            "write_timeout": 1.0,
            "xonxoff": config.flow_control == "xonxoff",
            "rtscts": config.flow_control == "rtscts",
            "dsrdtr": config.flow_control == "dsrdtr",
        }
        serial_port: serial.SerialBase | None = None
        try:
            serial_port = self._serial_factory(**settings)
            serial_port.dtr = config.dtr
            serial_port.rts = config.rts
        except (serial.SerialException, OSError, ValueError) as exc:
            if serial_port is not None:
                with suppress(serial.SerialException, OSError):
                    serial_port.close()
            raise _map_serial_error(exc) from exc
        self._serial = serial_port

    def close(self, timeout: float) -> None:
        """关闭底层串口。"""
        if timeout < 0:
            raise TransportIOError("关闭超时不能为负数。")
        if self._serial is None:
            return
        try:
            self._serial.close()
        except (serial.SerialException, OSError) as exc:
            raise _map_serial_error(exc) from exc
        finally:
            self._serial = None

    def read(self, max_bytes: int, timeout: float) -> bytes:
        """读取最多 max_bytes 个字节。"""
        serial_port = self._require_open_port()
        if max_bytes <= 0:
            raise TransportIOError("读取长度必须为正整数。")
        if timeout < 0:
            raise TransportIOError("读取超时不能为负数。")
        try:
            serial_port.timeout = timeout
            data = serial_port.read(max_bytes)
        except (serial.SerialException, OSError, ValueError) as exc:
            raise _map_serial_error(exc) from exc
        if not isinstance(data, bytes):
            raise TransportIOError("串口读取结果必须是 bytes。")
        return data

    def write_all(self, data: bytes, timeout: float) -> None:
        """循环写入直到全部发送成功或超时。"""
        serial_port = self._require_open_port()
        if not isinstance(data, bytes) or not data:
            raise TransportIOError("写入数据必须是非空 bytes。")
        if timeout <= 0:
            raise TransportIOError("写入超时必须大于零。")
        deadline = self._monotonic() + timeout
        try:
            serial_port.write_timeout = timeout
            pending = data
            while pending:
                written = serial_port.write(pending)
                if not written:
                    raise TransportIOError("串口未写入任何数据。")
                pending = pending[written:]
                if pending and self._monotonic() >= deadline:
                    raise TransportIOError("串口写入超时。")
        except (serial.SerialException, OSError, ValueError) as exc:
            raise _map_serial_error(exc) from exc

    def set_line_state(self, *, dtr: bool, rts: bool) -> None:
        """修改 DTR 和 RTS 状态。"""
        serial_port = self._require_open_port()
        try:
            serial_port.dtr = dtr
            serial_port.rts = rts
        except (serial.SerialException, OSError, ValueError) as exc:
            raise _map_serial_error(exc) from exc

    @property
    def is_open(self) -> bool:
        """返回串口是否已成功打开。"""
        if self._serial is None:
            return False
        try:
            return bool(self._serial.is_open)
        except (serial.SerialException, OSError):
            return False

    def _require_open_port(self) -> serial.SerialBase:
        serial_port = self._serial
        if serial_port is None or not self.is_open:
            raise TransportIOError("串口尚未打开。")
        return serial_port
