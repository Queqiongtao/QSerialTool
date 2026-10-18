#!/usr/bin/env python3
"""QSerialTool 稳定性监控：定时采样进程内存、句柄与日志文件增长。

用于实施计划 §17.6 的长时间稳定性验收（例如 2 小时接收）：持续采样目标
进程的私有内存、工作集与句柄数，同时记录自动日志文件大小，写入 CSV；
结束时输出增长摘要并按阈值给出判定。

Windows 使用 psapi 采样；其他平台回退读取 /proc。进程名匹配不区分大小写。
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

DEFAULT_PROCESS = "QSerialTool.exe"
DEFAULT_INTERVAL_S = 30.0
DEFAULT_DURATION_S = 7200.0
DEFAULT_MAX_GROWTH_MB = 50.0
# 稳定性判定跳过前 5 分钟热身，避免启动期缓存增长被计入泄漏。
WARMUP_SECONDS = 300.0


def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process", default=DEFAULT_PROCESS, help="目标进程名")
    parser.add_argument("--pid", type=int, help="直接指定进程 PID（优先于进程名匹配）")
    parser.add_argument(
        "--log-file",
        help="自动日志文件或目录路径（可选；目录会累计其中所有文件大小）",
    )
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S, help="采样间隔秒")
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION_S, help="监控总时长秒")
    parser.add_argument("--csv", default="stability.csv", help="采样明细输出路径")
    parser.add_argument(
        "--max-growth-mb",
        type=float,
        default=DEFAULT_MAX_GROWTH_MB,
        help="热身 5 分钟后私有内存允许的最大增长（MiB）",
    )
    return parser


if sys.platform.startswith("win"):

    class _PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_uint32),
            ("PageFaultCount", ctypes.c_uint32),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    def _windows_pids(process_name: str) -> list[int]:
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.QueryFullProcessImageNameW.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        )
        ctypes.windll.psapi.EnumProcesses.argtypes = (
            ctypes.POINTER(wintypes.DWORD),
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        )
        buffer = (wintypes.DWORD * 4096)()
        needed = wintypes.DWORD()
        if not ctypes.windll.psapi.EnumProcesses(
            buffer, ctypes.sizeof(buffer), ctypes.byref(needed)
        ):
            return []
        found: list[int] = []
        for index in range(needed.value // ctypes.sizeof(wintypes.DWORD)):
            pid = buffer[index]
            if not pid:
                continue
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                continue
            try:
                path = ctypes.create_unicode_buffer(512)
                size = wintypes.DWORD(512)
                if (
                    kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size))
                    and os.path.basename(path.value).lower() == process_name.lower()
                ):
                    found.append(pid)
            finally:
                kernel32.CloseHandle(handle)
        return found

    def _windows_stats(pid: int) -> tuple[float, float, int] | None:
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        handle = kernel32.OpenProcess(0x1000 | 0x0400, False, pid)
        if not handle:
            return None
        try:
            counters = _PROCESS_MEMORY_COUNTERS_EX()
            counters.cb = ctypes.sizeof(counters)
            if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return None
            handles = wintypes.DWORD()
            kernel32.GetProcessHandleCount(handle, ctypes.byref(handles))
            private_mb = counters.PrivateUsage / (1024 * 1024)
            working_mb = counters.WorkingSetSize / (1024 * 1024)
            return private_mb, working_mb, handles.value
        finally:
            kernel32.CloseHandle(handle)

    def find_pids(process_name: str) -> list[int]:
        """返回全部匹配进程的 PID。"""
        return _windows_pids(process_name)

    def sample_stats(pid: int) -> tuple[float, float, int] | None:
        """返回 (私有内存 MiB, 工作集 MiB, 句柄数)。"""
        return _windows_stats(pid)

else:

    def find_pids(process_name: str) -> list[int]:
        """返回全部匹配进程的 PID。"""
        found: list[int] = []
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                name = (entry / "comm").read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if name.lower() == process_name.lower():
                found.append(int(entry.name))
        return found

    def sample_stats(pid: int) -> tuple[float, float, int] | None:
        """返回 (私有内存 MiB, 工作集 MiB, 句柄数)；句柄数在 Linux 下恒为 0。"""
        try:
            status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
        except OSError:
            return None
        values: dict[str, int] = {}
        for line in status.splitlines():
            key, _, value = line.partition(":")
            if key in {"VmRSS", "VmData"}:
                values[key] = int(value.split()[0]) * 1024
        rss = values.get("VmRSS", 0) / (1024 * 1024)
        private = values.get("VmData", 0) / (1024 * 1024)
        return private, rss, 0


def log_size(log_path: Path | None) -> int:
    """返回日志文件或目录内全部文件的总字节数。"""
    if log_path is None:
        return 0
    try:
        if log_path.is_dir():
            return sum(file.stat().st_size for file in log_path.iterdir() if file.is_file())
        return log_path.stat().st_size
    except OSError:
        return 0


def main(argv: list[str] | None = None) -> int:
    """执行采样循环并输出增长摘要。"""
    arguments = build_parser().parse_args(argv)
    log_path = Path(arguments.log_file) if arguments.log_file else None
    csv_path = Path(arguments.csv)
    deadline = time.monotonic() + arguments.duration
    rows: list[tuple[float, int, float, float, int, int]] = []
    missing_reported = False
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["monotonic_s", "pid", "private_mb", "working_set_mb", "handles", "log_bytes"]
        )
        while time.monotonic() < deadline:
            pids = [arguments.pid] if arguments.pid else find_pids(arguments.process)
            samples = [(pid, sample_stats(pid)) for pid in pids]
            samples = [(pid, stats) for pid, stats in samples if stats is not None]
            if not samples:
                if not missing_reported:
                    print(f"未找到进程 {arguments.process}，等待启动…", file=sys.stderr)
                    missing_reported = True
            else:
                missing_reported = False
                # PyInstaller 单文件会同时存在引导进程与主进程，取私有内存最大的一个。
                pid, stats = max(samples, key=lambda item: item[1][0])
                assert stats is not None
                private_mb, working_mb, handles = stats
                log_bytes = log_size(log_path)
                elapsed = arguments.duration - (deadline - time.monotonic())
                writer.writerow(
                    [
                        f"{elapsed:.1f}",
                        pid,
                        f"{private_mb:.1f}",
                        f"{working_mb:.1f}",
                        handles,
                        log_bytes,
                    ]
                )
                stream.flush()
                print(
                    f"[{elapsed:7.1f}s] pid={pid} private={private_mb:7.1f} MiB "
                    f"working={working_mb:7.1f} MiB handles={handles} log={log_bytes} B"
                )
                rows.append((elapsed, pid, private_mb, working_mb, handles, log_bytes))
            time.sleep(arguments.interval)

    if not rows:
        print("未采集到任何样本。", file=sys.stderr)
        return 1
    warmup = [row for row in rows if row[0] >= WARMUP_SECONDS] or rows[-5:]
    baseline = warmup[0][2]
    peak = max(row[2] for row in rows)
    growth = peak - baseline
    handle_growth = warmup[-1][4] - warmup[0][4]
    log_growth = rows[-1][5] - rows[0][5]
    print("--- 摘要 ---")
    print(f"样本数={len(rows)} 基线私有内存={baseline:.1f} MiB 峰值={peak:.1f} MiB")
    print(f"监控期内私有内存增长={growth:.1f} MiB（阈值 {arguments.max_growth_mb:.0f}）")
    print(f"句柄变化={handle_growth} 日志增长={log_growth} 字节")
    verdict = "PASS" if growth <= arguments.max_growth_mb else "FAIL"
    print(f"STABILITY {verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
