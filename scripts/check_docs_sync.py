#!/usr/bin/env python3
"""检查代码变更是否在同一提交中同步了相关文档。"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RULE_FILE = ROOT / "docs" / "doc-sync-rules.json"


@dataclass(frozen=True, slots=True)
class SyncRule:
    """一条源码路径到文档路径的同步约束。"""

    name: str
    sources: tuple[str, ...]
    required_any: tuple[str, ...]

    def matches_source(self, path: str) -> bool:
        """判断路径是否触发该规则。"""
        return _matches_any(path, self.sources)

    def has_documentation_update(self, changed_paths: set[str]) -> bool:
        """判断变更集中是否包含该规则要求的文档。"""
        return any(_matches_any(path, self.required_any) for path in changed_paths)


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    normalized = path.replace("\\", "/")
    for pattern in patterns:
        if fnmatch.fnmatchcase(normalized, pattern):
            return True
        # fnmatch treats "**/" as requiring at least one directory. A glob such as
        # "docs/adr/**/*.md" should also match files directly under docs/adr.
        if "**/" in pattern and fnmatch.fnmatchcase(normalized, pattern.replace("**/", "")):
            return True
    return False


def _load_rule_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取文档同步规则 {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("文档同步规则根节点必须是对象。")
    return payload


def _require_string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} 必须是非空字符串数组。")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field_name} 必须是非空字符串数组。")
    return tuple(item.strip().replace("\\", "/") for item in value)


def load_rules(path: Path = RULE_FILE) -> tuple[tuple[SyncRule, ...], tuple[str, ...]]:
    """读取并验证文档同步规则。"""
    payload = _load_rule_payload(path)
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ValueError("rules 必须是非空数组。")
    rules: list[SyncRule] = []
    names: set[str] = set()
    for index, raw_rule in enumerate(raw_rules):
        if not isinstance(raw_rule, dict):
            raise ValueError(f"rules[{index}] 必须是对象。")
        name = raw_rule.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"rules[{index}].name 必须是非空字符串。")
        if name in names:
            raise ValueError(f"规则名称重复：{name}")
        names.add(name)
        rules.append(
            SyncRule(
                name=name,
                sources=_require_string_tuple(raw_rule.get("sources"), f"rules[{index}].sources"),
                required_any=_require_string_tuple(
                    raw_rule.get("required_any"),
                    f"rules[{index}].required_any",
                ),
            )
        )
    unmapped_fail = _require_string_tuple(payload.get("unmapped_fail"), "unmapped_fail")
    return tuple(rules), unmapped_fail


def _target_exists(root: Path, pattern: str) -> bool:
    if any(character in pattern for character in "*?["):
        return any(root.glob(pattern))
    return (root / pattern).exists()


def validate_rule_targets(
    root: Path = ROOT,
    rules: tuple[SyncRule, ...] | None = None,
) -> list[str]:
    """确认每个规则要求的文档目标至少存在一个文件。"""
    selected_rules = rules if rules is not None else load_rules()[0]
    problems: list[str] = []
    for rule in selected_rules:
        if not any(_target_exists(root, pattern) for pattern in rule.required_any):
            problems.append(f"规则 {rule.name} 的文档目标均不存在：{', '.join(rule.required_any)}")
    return problems


def find_sync_issues(
    changed_paths: set[str],
    rules: tuple[SyncRule, ...],
    unmapped_fail: tuple[str, ...],
) -> list[str]:
    """返回变更集违反同步规则的问题列表。"""
    normalized_paths = {path.replace("\\", "/") for path in changed_paths}
    issues: list[str] = []
    covered_paths: set[str] = set()
    for rule in rules:
        matched_sources = {path for path in normalized_paths if rule.matches_source(path)}
        if not matched_sources:
            continue
        covered_paths.update(matched_sources)
        if not rule.has_documentation_update(normalized_paths):
            issues.append(
                f"{rule.name}：{', '.join(sorted(matched_sources))} 需要同步更新 "
                f"{' 或 '.join(rule.required_any)} 中的至少一个文件。"
            )
    for path in sorted(normalized_paths - covered_paths):
        if _matches_any(path, unmapped_fail):
            issues.append(f"未配置文档同步规则的运行时代码：{path}")
    return issues


def _run_git(*arguments: str) -> set[str]:
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
        raise RuntimeError(f"Git 命令失败：{' '.join(command)}\n{detail}")
    return {
        line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()
    }


def changed_paths(mode: str, base: str | None = None) -> set[str]:
    """按指定模式读取需要检查的变更路径。"""
    common = ("--name-only", "--diff-filter=ACMR")
    if mode == "staged":
        return _run_git("diff", "--cached", *common)
    if mode == "working-tree":
        changed = _run_git("diff", *common, "HEAD")
        changed.update(_run_git("ls-files", "--others", "--exclude-standard"))
        return changed
    if mode == "base":
        if not base:
            raise ValueError("--base 模式必须提供 Git 引用。")
        return _run_git("diff", *common, f"{base}...HEAD")
    raise ValueError(f"不支持的检查模式：{mode}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--staged", action="store_true", help="检查暂存区相对 HEAD 的变更。")
    modes.add_argument("--base", metavar="REF", help="检查 REF...HEAD 范围内的变更。")
    modes.add_argument(
        "--working-tree",
        action="store_true",
        help="检查工作区和暂存区相对 HEAD 的变更。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """执行文档同步检查并返回进程退出码。"""
    arguments = _build_parser().parse_args(argv)
    try:
        rules, unmapped_fail = load_rules()
        problems = validate_rule_targets(RULE_FILE.parent.parent, rules)
        if arguments.staged:
            mode = "staged"
            base = None
        elif arguments.working_tree:
            mode = "working-tree"
            base = None
        else:
            mode = "base"
            base = arguments.base
        paths = changed_paths(mode, base)
        problems.extend(find_sync_issues(paths, rules, unmapped_fail))
    except (RuntimeError, ValueError) as exc:
        print(f"[doc-sync] 配置或 Git 检查失败：{exc}", file=sys.stderr)
        return 2

    if problems:
        print("[doc-sync] 文档同步检查未通过：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "[doc-sync] 请在同一提交中更新对应文档；规则见 docs/doc-sync-rules.json。",
            file=sys.stderr,
        )
        return 1
    print(f"[doc-sync] 通过，共检查 {len(paths)} 个变更路径。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
