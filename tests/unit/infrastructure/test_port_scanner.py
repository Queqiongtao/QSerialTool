"""测试 pyserial 端口枚举适配。"""

from dataclasses import dataclass

from qserialtool.infrastructure import SerialPortScanner


@dataclass
class FakePort:
    device: str


def test_port_scanner_sorts_ports_naturally_and_removes_empty_values() -> None:
    scanner = SerialPortScanner(
        list_function=lambda: [FakePort("COM10"), FakePort("COM2"), FakePort("")]
    )

    assert scanner.list_ports() == ("COM2", "COM10")


def test_port_scanner_returns_empty_tuple_on_enumeration_error() -> None:
    def fail() -> list[FakePort]:
        raise OSError("enumeration failed")

    scanner = SerialPortScanner(list_function=fail)
    assert scanner.list_ports() == ()
