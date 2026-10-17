"""真实串口硬件验收用例（默认跳过）。

需要两个交叉接线（TX↔RX、共地）的 USB 转串口模块，并设置环境变量
``QSERIALTOOL_HW_PORTS=应用端口,对端端口``（例如 ``COM21,COM5``）后运行：

    QSERIALTOOL_HW_PORTS=COM21,COM5 python -m pytest -m hardware \
        tests/integration/test_real_serial_hardware.py

覆盖实施计划 §17.5 中可自动化的场景：文本/HEX 字节一致、GB18030 中文、
波特率矩阵、高频接收与暂停、周期发送停止、端口占用错误。运行中拔插与两小时
稳定性按发布清单人工执行。
"""

from __future__ import annotations

import os
import threading

import pytest
import serial
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from tests.fixtures.fakes import FakeClock
from tests.fixtures.ui_helpers import current_tab

from qserialtool.application import SessionManager
from qserialtool.domain import SessionState
from qserialtool.infrastructure import SerialTransport
from qserialtool.ui import MainWindow

pytestmark = pytest.mark.hardware

_TEXT = "QSerialTool 回环测试 ABC 123"
_GB18030_TEXT = "串口工具硬件验收：中文编码 GB18030。"


def _hardware_ports() -> tuple[str, str]:
    value = os.environ.get("QSERIALTOOL_HW_PORTS", "")
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if len(parts) != 2:
        pytest.skip("设置 QSERIALTOOL_HW_PORTS=应用端口,对端端口 后运行硬件验收")
    return parts[0], parts[1]


def _build_window(qtbot: object) -> MainWindow:
    manager = SessionManager(transport_factory=SerialTransport, clock=FakeClock())
    window = MainWindow(session_manager=manager, port_provider=lambda: ())
    qtbot.addWidget(window)
    window.show()
    return window


def _connect(
    qtbot: object,
    tab: object,
    port: str,
    *,
    baud: int = 115200,
    encoding: str = "utf-8",
) -> None:
    panel = tab.connection_panel
    panel.port_combo.setEditText(port)
    panel.baud_combo.setEditText(str(baud))
    index = panel.encoding_combo.findData(encoding)
    if index >= 0:
        panel.encoding_combo.setCurrentIndex(index)
    qtbot.mouseClick(panel.connect_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: (
            tab.controller.state is SessionState.CONNECTED
            and tab.send_panel.send_button.isEnabled()
        ),
        timeout=5000,
    )


def _disconnect(qtbot: object, tab: object) -> None:
    if tab.controller.state is SessionState.CONNECTED:
        qtbot.mouseClick(tab.connection_panel.connect_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(
            lambda: tab.controller.state is SessionState.DISCONNECTED,
            timeout=5000,
        )


class _EchoPeer:
    """后台线程把对端串口收到的字节原样回显。"""

    def __init__(self, port: str, baud: int = 115200) -> None:
        self._serial = serial.Serial(port, baud, timeout=0.05, write_timeout=2)
        self._stop = threading.Event()
        self.received = 0
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> _EchoPeer:
        self._serial.reset_input_buffer()
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop.is_set():
            chunk = self._serial.read(4096)
            if not chunk:
                continue
            self.received += len(chunk)
            self._serial.write(chunk)
            self._serial.flush()

    def __exit__(self, *exc_info: object) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._serial.close()


def _wait_rx(qtbot: object, tab: object, marker: str) -> None:
    """等待接收区出现带 RX 前缀的指定内容，避免误匹配同屏的 TX 回显。"""
    qtbot.waitUntil(
        lambda: f"RX: {marker}" in tab.receive_panel.output.toPlainText(),
        timeout=5000,
    )


def test_text_roundtrip_echo(qtbot: object) -> None:
    app_port, peer_port = _hardware_ports()
    window = _build_window(qtbot)
    tab = current_tab(window)
    try:
        with _EchoPeer(peer_port) as peer:
            _connect(qtbot, tab, app_port)
            tab.send_panel.editor.setPlainText(_TEXT)
            qtbot.mouseClick(tab.send_panel.send_button, Qt.MouseButton.LeftButton)
            _wait_rx(qtbot, tab, _TEXT)
            assert peer.received >= len(_TEXT.encode("utf-8"))
    finally:
        tab.controller.close(force=True)
        window.close()


def test_hex_binary_roundtrip(qtbot: object) -> None:
    app_port, peer_port = _hardware_ports()
    payload = bytes(range(256))
    hex_text = " ".join(f"{value:02X}" for value in payload)
    window = _build_window(qtbot)
    tab = current_tab(window)
    try:
        with _EchoPeer(peer_port) as peer:
            _connect(qtbot, tab, app_port)
            receive_modes = tab.receive_panel.mode_combo
            receive_modes.setCurrentIndex(receive_modes.findData("hex"))
            send_modes = tab.send_panel.mode_combo
            send_modes.setCurrentIndex(send_modes.findData("hex"))
            tab.send_panel.editor.setPlainText(hex_text)
            qtbot.mouseClick(tab.send_panel.send_button, Qt.MouseButton.LeftButton)
            _wait_rx(qtbot, tab, "00 01 02 03")
            assert "FD FE FF" in tab.receive_panel.output.toPlainText()
            assert peer.received >= len(payload)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_gb18030_bidirectional(qtbot: object) -> None:
    app_port, peer_port = _hardware_ports()
    window = _build_window(qtbot)
    tab = current_tab(window)
    peer = serial.Serial(peer_port, 115200, timeout=2, write_timeout=2)
    try:
        _connect(qtbot, tab, app_port, encoding="gb18030")
        peer.reset_input_buffer()
        peer.write(_GB18030_TEXT.encode("gb18030") + b"\r\n")
        peer.flush()
        qtbot.waitUntil(
            lambda: _GB18030_TEXT in tab.receive_panel.output.toPlainText(), timeout=5000
        )

        sent = "中文发送测试"
        tab.send_panel.editor.setPlainText(sent)
        qtbot.mouseClick(tab.send_panel.send_button, Qt.MouseButton.LeftButton)
        received = peer.read(len(sent.encode("gb18030")) + 2)
        assert sent.encode("gb18030") in received
    finally:
        peer.close()
        tab.controller.close(force=True)
        window.close()


def test_baudrate_matrix(qtbot: object) -> None:
    app_port, peer_port = _hardware_ports()
    window = _build_window(qtbot)
    tab = current_tab(window)
    try:
        for baud in (9600, 115200, 921600):
            _connect(qtbot, tab, app_port, baud=baud)
            with _EchoPeer(peer_port, baud) as peer:
                marker = f"baud-{baud}"
                tab.send_panel.editor.setPlainText(marker)
                qtbot.mouseClick(tab.send_panel.send_button, Qt.MouseButton.LeftButton)
                _wait_rx(qtbot, tab, marker)
                assert peer.received >= len(marker)
            _disconnect(qtbot, tab)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_high_frequency_receive_pause_and_resume(qtbot: object) -> None:
    app_port, peer_port = _hardware_ports()
    window = _build_window(qtbot)
    tab = current_tab(window)
    peer = serial.Serial(peer_port, 115200, timeout=0.2, write_timeout=2)
    stop = threading.Event()

    def stream() -> None:
        index = 0
        while not stop.is_set():
            index += 1
            try:
                peer.write(f"[{index:05d}] high frequency payload\r\n".encode("ascii"))
                peer.flush()
            except serial.SerialException:
                return

    worker = threading.Thread(target=stream, daemon=True)
    try:
        _connect(qtbot, tab, app_port)
        worker.start()
        qtbot.waitUntil(
            lambda: "[00200] high frequency payload" in tab.receive_panel.output.toPlainText(),
            timeout=10000,
        )

        qtbot.mouseClick(tab.receive_panel.pause_button, Qt.MouseButton.LeftButton)
        assert tab.receive_panel.pause_button.text() == "继续"
        frozen = len(tab.receive_panel.output.toPlainText())
        qtbot.wait(500)
        assert len(tab.receive_panel.output.toPlainText()) == frozen

        qtbot.mouseClick(tab.receive_panel.pause_button, Qt.MouseButton.LeftButton)
        assert tab.receive_panel.pause_button.text() == "暂停"
        qtbot.waitUntil(lambda: len(tab.receive_panel.output.toPlainText()) > frozen, timeout=5000)
    finally:
        stop.set()
        worker.join(timeout=2)
        peer.close()
        tab.controller.close(force=True)
        window.close()


def test_periodic_send_stops_promptly(qtbot: object) -> None:
    app_port, peer_port = _hardware_ports()
    window = _build_window(qtbot)
    tab = current_tab(window)
    try:
        with _EchoPeer(peer_port) as peer:
            _connect(qtbot, tab, app_port)
            tab.send_panel.editor.setPlainText("tick")
            tab.send_panel.interval_spin.setValue(20)
            qtbot.mouseClick(tab.send_panel.periodic_button, Qt.MouseButton.LeftButton)
            assert tab.send_panel.periodic_button.isChecked()
            qtbot.waitUntil(lambda: peer.received >= 20, timeout=5000)

            qtbot.mouseClick(tab.send_panel.periodic_button, Qt.MouseButton.LeftButton)
            assert not tab.send_panel.periodic_button.isChecked()
            # 先排空已在传输途中的数据，再确认发送计数不再增长。
            qtbot.wait(400)
            stopped_at = peer.received
            qtbot.wait(400)
            assert peer.received == stopped_at
    finally:
        tab.controller.close(force=True)
        window.close()


def test_busy_port_reports_error_and_keeps_config(
    qtbot: object,
    monkeypatch: object,
) -> None:
    app_port, _peer_port = _hardware_ports()
    warnings: list[object] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args))
    window = _build_window(qtbot)
    tab = current_tab(window)
    holder = serial.Serial(app_port, 115200)
    try:
        tab.connection_panel.port_combo.setEditText(app_port)
        qtbot.mouseClick(tab.connection_panel.connect_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: tab.controller.state is SessionState.ERROR, timeout=5000)
        assert tab.connection_panel.port_combo.currentText() == app_port
        assert warnings
    finally:
        holder.close()
        tab.controller.close(force=True)
        window.close()
