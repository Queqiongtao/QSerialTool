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
import time

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


@pytest.fixture(autouse=True)
def _silence_dialogs(monkeypatch: object) -> None:
    """静音模态对话框：无人值守跑压力/稳定性时避免事件循环被弹窗阻塞。"""
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )


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
        # 状态切换由控制器先完成，错误快照经 queued signal 到达界面后才弹窗；
        # 在高频/快速失败路径上两步之间存在竞态，这里等待错误提示实际发生。
        qtbot.waitUntil(lambda: bool(warnings), timeout=5000)
        assert tab.connection_panel.port_combo.currentText() == app_port
    finally:
        holder.close()
        tab.controller.close(force=True)
        window.close()


class _StressPeer:
    """持续发送压力流并回显应用数据的对端驱动。"""

    def __init__(self, port: str, baud: int, interval_ms: float) -> None:
        # timeout=0：读操作立即返回，避免回显读把发送节奏拖慢到读超时级别。
        self._serial = serial.Serial(port, baud, timeout=0, write_timeout=5)
        self._interval = interval_ms / 1000
        self._stop = threading.Event()
        self.received = 0
        self.sent = 0
        self.errors: list[str] = []
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> _StressPeer:
        self._serial.reset_input_buffer()
        self._thread.start()
        return self

    def _run(self) -> None:
        index = 0
        last_send = time.monotonic()
        try:
            while not self._stop.is_set():
                chunk = self._serial.read(8192)
                if chunk:
                    self.received += len(chunk)
                    self._serial.write(chunk)
                    self._serial.flush()
                now = time.monotonic()
                if now - last_send >= self._interval:
                    index += 1
                    payload = f"[{index:06d}] stress payload {'x' * 32}\r\n".encode("ascii")
                    self._serial.write(payload)
                    self._serial.flush()
                    self.sent += len(payload)
                    last_send = now
                else:
                    time.sleep(0.0005)
        except Exception as exc:
            self.errors.append(str(exc))

    def __exit__(self, *exc_info: object) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._serial.close()


def test_duplex_stress(qtbot: object) -> None:
    """全双工压力：对端持续流 + 应用周期发送，期间做 UI 操作冒烟。

    压力时长由 ``QSERIALTOOL_HW_STRESS_SECONDS`` 控制（默认 60 秒）。
    重载下周期发送可能因有界写队列已满而自动停止（设计如此），测试接受
    两种状态，只要求停止后发送计数不再增长。
    """
    app_port, peer_port = _hardware_ports()
    duration = float(os.environ.get("QSERIALTOOL_HW_STRESS_SECONDS", "60"))
    window = _build_window(qtbot)
    tab = current_tab(window)
    try:
        _connect(qtbot, tab, app_port, baud=921600)
        with _StressPeer(peer_port, 921600, interval_ms=2) as peer:
            tab.send_panel.editor.setPlainText("stress-ping")
            tab.send_panel.interval_spin.setValue(10)
            qtbot.mouseClick(tab.send_panel.periodic_button, Qt.MouseButton.LeftButton)
            assert tab.send_panel.periodic_button.isChecked()

            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                qtbot.wait(200)
                assert tab.controller.state is SessionState.CONNECTED
                assert tab.controller.snapshot.last_error is None

            qtbot.mouseClick(tab.receive_panel.pause_button, Qt.MouseButton.LeftButton)
            assert tab.receive_panel.pause_button.text() == "继续"
            qtbot.mouseClick(tab.receive_panel.pause_button, Qt.MouseButton.LeftButton)
            assert tab.receive_panel.pause_button.text() == "暂停"
            tab.set_view_mode("terminal", persist=False)
            tab.set_view_mode("split", persist=False)
            qtbot.mouseClick(tab.receive_panel.clear_button, Qt.MouseButton.LeftButton)
            qtbot.wait(200)
            assert tab.controller.state is SessionState.CONNECTED

            if tab.send_panel.periodic_button.isChecked():
                qtbot.mouseClick(tab.send_panel.periodic_button, Qt.MouseButton.LeftButton)
            assert not tab.send_panel.periodic_button.isChecked()
            # 写队列中可能仍有已排队的周期任务在陆续发出，先等排空再确认计数不再增长。
            qtbot.wait(3000)
            stopped_at = peer.received
            qtbot.wait(1000)
            assert peer.received == stopped_at
            assert not peer.errors
            assert peer.sent > 0
    finally:
        tab.controller.close(force=True)
        window.close()


def test_binary_burst_integrity(qtbot: object) -> None:
    """对端突发发送 1 MiB 二进制数据，累计接收字节必须完全一致。

    接收路径对有意的跨块多字节字符尾巴会暂存到断开时补记，因此先核对
    ``rx_bytes`` 累计值，再断开并验证尾字节已补进内存缓冲。
    """
    app_port, peer_port = _hardware_ports()
    total = 1024 * 1024
    window = _build_window(qtbot)
    tab = current_tab(window)
    peer = serial.Serial(peer_port, 921600, timeout=0.1, write_timeout=10)
    try:
        _connect(qtbot, tab, app_port, baud=921600)
        baseline = tab.controller.snapshot.rx_bytes
        block = bytes(range(256)) * 16
        sent = 0
        while sent < total:
            chunk = block[: min(len(block), total - sent)]
            written = peer.write(chunk)
            sent += written
        peer.flush()
        qtbot.waitUntil(
            lambda: tab.controller.snapshot.rx_bytes - baseline >= total, timeout=180000
        )
        assert tab.controller.snapshot.rx_bytes - baseline == total
        assert tab.controller.state is SessionState.CONNECTED

        _disconnect(qtbot, tab)
        buffered = sum(
            len(record.raw) for record in tab.controller.records if record.direction == "rx"
        )
        assert buffered == total
    finally:
        peer.close()
        tab.controller.close(force=True)
        window.close()
