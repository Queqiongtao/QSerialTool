"""系统串口枚举实现。"""

import re
from collections.abc import Callable, Iterable

from serial.tools import list_ports

from qserialtool.domain import PortInfo


def _natural_port_key(port_name: str) -> tuple[object, ...]:
    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", port_name)
        if part
    )


def _clean_description(device: str, description: str) -> str:
    """去掉描述里重复的设备名，缺失时返回空字符串。"""
    cleaned = re.sub(
        rf"\s*\({re.escape(device)}\)\s*$",
        "",
        description,
        flags=re.IGNORECASE,
    ).strip()
    basename = device.rsplit("/", 1)[-1]
    if cleaned.casefold() in {device.casefold(), basename.casefold()}:
        return ""
    return cleaned


class SerialPortScanner:
    """使用 pyserial 枚举当前系统串口。"""

    def __init__(self, list_function: Callable[[], Iterable[object]] = list_ports.comports) -> None:
        self._list_function = list_function

    def list_ports(self) -> tuple[PortInfo, ...]:
        """返回按自然顺序排序的端口名称与描述。"""
        try:
            ports = self._list_function()
        except (OSError, RuntimeError):
            return ()
        found: dict[str, str] = {}
        for port in ports:
            device = str(getattr(port, "device", "")).strip()
            if not device:
                continue
            description = _clean_description(
                device,
                str(getattr(port, "description", "") or "").strip(),
            )
            if device not in found or (not found[device] and description):
                found[device] = description
        return tuple(
            PortInfo(device=device, description=found[device])
            for device in sorted(found, key=_natural_port_key)
        )
