#!/usr/bin/env python3
"""真实串口验收的对端驱动。

在交叉接线（TX↔RX、共地）的两个 USB 转串口模块上，一端由 QSerialTool
连接，另一端运行本脚本回显、注入或校验字节，用于实施计划 §17.5 的硬件
验收。默认参数面向 115200 8N1、无流控。

模式：
- echo：原样回显收到的字节，持续 duration 秒；
- verify：读取并校验 expect-hex 指定的字节序列，超时或内容不符时返回非零；
- text / gb18030：按行发送示例文本，共 count 条；
- binary：循环发送 0x00-0xFF，共 count 轮；
- stream：按 interval-ms 间隔持续输出递增行，模拟设备启动日志与高频数据。
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time

import serial

DEFAULT_BAUD = 115200

_TEXT_LINES = (
    "QSerialTool hardware acceptance line",
    "0123456789",
    "abcdefghijklmnopqrstuvwxyz",
)
_GB18030_LINES = (
    "串口工具硬件验收：中文编码 GB18030 跨块传输。",
    "串口调试助手：中文显示不得乱码。",
)


def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="对端串口，例如 COM5")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help="波特率")
    parser.add_argument(
        "--mode",
        choices=("echo", "verify", "text", "gb18030", "binary", "stream"),
        default="echo",
        help="对端工作模式",
    )
    parser.add_argument("--expect-hex", help="verify 模式期望的十六进制字节串")
    parser.add_argument("--count", type=int, default=20, help="text/gb18030/binary 发送次数")
    parser.add_argument("--duration", type=float, default=30.0, help="echo/stream 持续秒数")
    parser.add_argument("--interval-ms", type=float, default=5.0, help="stream 发送间隔毫秒")
    parser.add_argument("--timeout", type=float, default=5.0, help="verify 读取超时秒数")
    return parser


def run_echo(port: serial.Serial, duration: float) -> int:
    """原样回显收到的字节。"""
    deadline = time.monotonic() + duration
    received = 0
    port.timeout = 0.05
    while time.monotonic() < deadline:
        chunk = port.read(4096)
        if not chunk:
            continue
        received += len(chunk)
        port.write(chunk)
        port.flush()
    print(f"echo finished: echoed {received} bytes")
    return 0


def run_verify(port: serial.Serial, expect_hex: str, timeout: float) -> int:
    """读取并校验期望字节序列。"""
    if not expect_hex:
        print("verify 模式需要 --expect-hex", file=sys.stderr)
        return 2
    expected = bytes.fromhex(expect_hex)
    port.timeout = 0.1
    data = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and len(data) < len(expected):
        data += port.read(len(expected) - len(data))
    ok = data == expected
    print(f"expected {len(expected)} bytes sha256={hashlib.sha256(expected).hexdigest()[:16]}")
    print(f"received {len(data)} bytes sha256={hashlib.sha256(data).hexdigest()[:16]}")
    if not ok:
        mismatch = next(
            (
                index
                for index, (actual, want) in enumerate(zip(data, expected, strict=False))
                if actual != want
            ),
            min(len(data), len(expected)),
        )
        print(f"first mismatch at byte {mismatch}")
    print("VERIFY PASS" if ok else "VERIFY FAIL")
    return 0 if ok else 1


def run_lines(port: serial.Serial, lines: tuple[str, ...], count: int, encoding: str) -> int:
    """按行发送示例文本。"""
    sent = 0
    for index in range(count):
        line = f"{lines[index % len(lines)]} #{index + 1}\r\n"
        payload = line.encode(encoding)
        port.write(payload)
        port.flush()
        sent += len(payload)
        time.sleep(0.002)
    print(f"sent {count} lines, {sent} bytes ({encoding})")
    return 0


def run_binary(port: serial.Serial, count: int) -> int:
    """循环发送 0x00-0xFF 全部字节。"""
    payload = bytes(range(256))
    for _ in range(count):
        port.write(payload)
        port.flush()
        time.sleep(0.002)
    print(f"sent 0x00-0xFF x{count} ({256 * count} bytes)")
    return 0


def run_stream(port: serial.Serial, duration: float, interval_s: float) -> int:
    """按固定间隔持续输出递增行，模拟高频设备日志。"""
    deadline = time.monotonic() + duration
    sent = 0
    index = 0
    while time.monotonic() < deadline:
        index += 1
        line = f"[{index:06d}] stream payload {'x' * 24}\r\n"
        payload = line.encode("ascii")
        port.write(payload)
        port.flush()
        sent += len(payload)
        time.sleep(interval_s)
    print(f"stream finished: {index} lines, {sent} bytes")
    return 0


def main(argv: list[str] | None = None) -> int:
    """执行对端模式并返回进程退出码。"""
    arguments = build_parser().parse_args(argv)
    with serial.Serial(arguments.port, arguments.baud, timeout=0.2, write_timeout=2) as port:
        port.reset_input_buffer()
        if arguments.mode == "echo":
            return run_echo(port, arguments.duration)
        if arguments.mode == "verify":
            return run_verify(port, arguments.expect_hex or "", arguments.timeout)
        if arguments.mode == "text":
            return run_lines(port, _TEXT_LINES, arguments.count, "ascii")
        if arguments.mode == "gb18030":
            return run_lines(port, _GB18030_LINES, arguments.count, "gb18030")
        if arguments.mode == "binary":
            return run_binary(port, arguments.count)
        return run_stream(port, arguments.duration, arguments.interval_ms / 1000)


if __name__ == "__main__":
    raise SystemExit(main())
