"""系统串口枚举实现。"""

import re
from collections.abc import Callable, Iterable

from serial.tools import list_ports


def _natural_port_key(port_name: str) -> tuple[object, ...]:
    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", port_name)
        if part
    )


class SerialPortScanner:
    """使用 pyserial 枚举当前系统串口。"""

    def __init__(self, list_function: Callable[[], Iterable[object]] = list_ports.comports) -> None:
        self._list_function = list_function

    def list_ports(self) -> tuple[str, ...]:
        """返回按自然顺序排序的端口名称。"""
        try:
            ports = self._list_function()
        except (OSError, RuntimeError):
            return ()
        names = {
            str(getattr(port, "device", "")).strip()
            for port in ports
            if str(getattr(port, "device", "")).strip()
        }
        return tuple(sorted(names, key=_natural_port_key))
