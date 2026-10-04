"""提交信息语言校验器单元测试。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "check_commit_message.py"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_commit_message", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载提交信息校验器。")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load_checker()

VALID_MESSAGE = "feat(ui): 增加提交信息中文检查\n\n- 新增 commit-msg 钩子并同步文档。\n"


def test_chinese_conventional_message_passes() -> None:
    assert checker.validate_message(VALID_MESSAGE) == []


def test_english_only_subject_fails() -> None:
    problems = checker.validate_message("feat(ui): add commit message check\n")

    assert "标题描述必须使用简体中文" in problems


def test_missing_type_prefix_fails() -> None:
    problems = checker.validate_message("增加提交信息中文检查\n")

    assert any("Conventional Commits" in problem for problem in problems)


def test_english_body_fails() -> None:
    problems = checker.validate_message("feat(ui): 增加检查\n\n- add hook and docs.\n")

    assert "提交正文必须使用简体中文" in problems


def test_comment_lines_are_ignored() -> None:
    text = "feat(ui): 增加检查\n\n# Please enter the commit message.\n# On branch main\n"

    assert checker.validate_message(text) == []


def test_empty_message_passes() -> None:
    assert checker.validate_message("\n# only comments\n") == []


@pytest.mark.parametrize("subject", ["Merge branch 'main'", 'Revert "feat: 旧提交"'])
def test_automatic_commits_are_skipped(subject: str) -> None:
    assert checker.validate_message(f"{subject}\n\nEnglish body is allowed here.\n") == []
