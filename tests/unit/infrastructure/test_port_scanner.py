"""测试 pyserial 端口枚举适配。"""

from dataclasses import dataclass

from qserialtool.domain import PortInfo
from qserialtool.infrastructure import SerialPortScanner


@dataclass
class FakePort:
    device: str
    description: str = ""


def test_port_scanner_sorts_ports_naturally_and_removes_empty_values() -> None:
    scanner = SerialPortScanner(
        list_function=lambda: [FakePort("COM10"), FakePort("COM2"), FakePort("")]
    )

    assert scanner.list_ports() == (
        PortInfo(device="COM2", description=""),
        PortInfo(device="COM10", description=""),
    )


def test_port_scanner_keeps_friendly_description_without_device_suffix() -> None:
    scanner = SerialPortScanner(
        list_function=lambda: [
            FakePort("COM5", "USB-Enhanced-SERIAL CH343 (COM5)"),
            FakePort("COM16", "USB-SERIAL CH340"),
        ]
    )

    assert scanner.list_ports() == (
        PortInfo(device="COM5", description="USB-Enhanced-SERIAL CH343"),
        PortInfo(device="COM16", description="USB-SERIAL CH340"),
    )


def test_port_scanner_drops_description_equal_to_device() -> None:
    scanner = SerialPortScanner(
        list_function=lambda: [
            FakePort("/dev/ttyUSB0", "ttyUSB0"),
            FakePort("/dev/ttyUSB1", "/dev/ttyUSB1"),
        ]
    )

    assert scanner.list_ports() == (
        PortInfo(device="/dev/ttyUSB0", description=""),
        PortInfo(device="/dev/ttyUSB1", description=""),
    )


def test_port_scanner_returns_empty_tuple_on_enumeration_error() -> None:
    def fail() -> list[FakePort]:
        raise OSError("enumeration failed")

    scanner = SerialPortScanner(list_function=fail)
    assert scanner.list_ports() == ()
