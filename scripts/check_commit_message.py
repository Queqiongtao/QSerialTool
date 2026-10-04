#!/usr/bin/env python3
"""校验提交信息符合“Conventional Commits 前缀 + 简体中文”规则。"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HEADER_PATTERN = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(\([^()\s]+\))?!?: \S"
)
CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SKIP_SUBJECT_PREFIXES = ("Merge ", "Revert ")


def strip_comments(text: str) -> str:
    """移除 Git 写入的注释行，保留其余内容。"""
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    return "\n".join(lines).strip()


def split_subject_and_body(text: str) -> tuple[str, str]:
    """按首个非空行拆分提交标题与正文。"""
    lines = text.replace("\r\n", "\n").split("\n")
    subject_index = next((index for index, line in enumerate(lines) if line.strip()), None)
    if subject_index is None:
        return "", ""
    subject = lines[subject_index].strip()
    body = "\n".join(lines[subject_index + 1 :]).strip()
    return subject, body


def validate_message(text: str) -> list[str]:
    """返回提交信息违反语言规范的说明列表。"""
    cleaned = strip_comments(text)
    if not cleaned:
        return []
    subject, body = split_subject_and_body(cleaned)
    if not subject or subject.startswith(SKIP_SUBJECT_PREFIXES):
        return []
    problems: list[str] = []
    if not HEADER_PATTERN.match(subject):
        problems.append("标题必须使用 Conventional Commits 类型前缀，例如 feat(ui): 修复图标显示")
    description = subject.split(": ", 1)[1] if ": " in subject else ""
    if not CJK_PATTERN.search(description):
        problems.append("标题描述必须使用简体中文")
    if body and not CJK_PATTERN.search(body):
        problems.append("提交正文必须使用简体中文")
    return problems


def _run_git(*arguments: str) -> str:
    command = ["git", "-C", str(ROOT), *arguments]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "未知 Git 错误"
        raise RuntimeError(f"Git 命令失败：{' '.join(arguments)}\n{detail}")
    return completed.stdout


def _message_of(revision: str) -> str:
    return _run_git("log", "-1", "--format=%B", revision)


def _subject_of(revision: str) -> str:
    return _run_git("log", "-1", "--format=%s", revision).strip()


def _range_revisions(base: str) -> list[str]:
    output = _run_git("rev-list", "--no-merges", f"{base}..HEAD")
    return [line.strip() for line in output.splitlines() if line.strip()]


def _validate_revision(revision: str, label: str) -> list[str]:
    if _subject_of(revision).startswith(SKIP_SUBJECT_PREFIXES):
        return []
    return [f"{label}：{problem}" for problem in validate_message(_message_of(revision))]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "message_file",
        nargs="?",
        help="Git 提交信息文件路径，由 commit-msg 钩子传入。",
    )
    parser.add_argument("--base", metavar="REF", help="校验 REF..HEAD 范围内的提交。")
    return parser


def main(argv: list[str] | None = None) -> int:
    """执行提交信息校验并返回进程退出码。"""
    arguments = _build_parser().parse_args(argv)
    try:
        if arguments.message_file:
            text = Path(arguments.message_file).read_text(encoding="utf-8")
            problems = validate_message(text)
        elif arguments.base:
            problems = []
            for revision in _range_revisions(arguments.base):
                problems.extend(_validate_revision(revision, revision[:12]))
        else:
            problems = _validate_revision("HEAD", "HEAD")
    except (OSError, RuntimeError) as exc:
        print(f"[commit-msg] 无法读取提交信息：{exc}", file=sys.stderr)
        return 2

    if problems:
        print("[commit-msg] 提交信息不符合规范：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "[commit-msg] 要求 Conventional Commits 英文类型前缀加简体中文标题与正文；"
            "合并与回滚自动提交跳过。规则见 AGENT.md 第 2 节。",
            file=sys.stderr,
        )
        return 1
    print("[commit-msg] 提交信息检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
