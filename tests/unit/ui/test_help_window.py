"""测试使用帮助窗口的入口、目录跳转与内容同步。"""

from pathlib import Path

from PySide6.QtGui import QKeySequence
from tests.fixtures.fakes import FakeClock, FakeTransport

from qserialtool.application import SessionManager
from qserialtool.domain import PortInfo
from qserialtool.ui import HelpWindow, MainWindow
from qserialtool.ui.help_window import _FALLBACK_TEXT
from qserialtool.ui.style_sheet import assets_dir

ROOT = Path(__file__).resolve().parents[3]
DOCS_GUIDE = ROOT / "docs" / "user-guide.md"
PACKAGED_GUIDE = assets_dir() / "user-guide.md"


def _window(qtbot: object) -> MainWindow:
    manager = SessionManager(
        transport_factory=FakeTransport,
        clock=FakeClock(),
    )
    window = MainWindow(
        session_manager=manager,
        port_provider=lambda: (PortInfo(device="COM1"),),
    )
    qtbot.addWidget(window)
    window.show()
    return window


def _open_help(qtbot: object) -> tuple[MainWindow, HelpWindow]:
    window = _window(qtbot)
    window._show_help()
    help_window = window._help_window
    assert isinstance(help_window, HelpWindow)
    qtbot.addWidget(help_window)
    return window, help_window


def test_help_action_is_in_menu_with_f1_shortcut(qtbot: object) -> None:
    window = _window(qtbot)
    try:
        assert window.help_action.text() == "使用帮助"
        assert window.help_action.shortcut() == QKeySequence("F1")
        assert window.help_action in window.main_menu.actions()
    finally:
        window.close()


def test_help_action_opens_single_reusable_window(qtbot: object) -> None:
    window, first = _open_help(qtbot)
    try:
        assert first.isVisible()
        window._show_help()
        assert window._help_window is first
    finally:
        window.close()


def test_help_toc_lists_sections_and_jumps(qtbot: object) -> None:
    window, help_window = _open_help(qtbot)
    try:
        assert help_window.toc.count() == 9
        assert help_window.toc.item(0).text() == "1. 安装与启动"
        help_window.toc.setCurrentRow(6)
        assert help_window.content.textCursor().block().text() == "7. 配置、退出与恢复"
    finally:
        window.close()


def test_help_renders_markdown_tables(qtbot: object) -> None:
    window, help_window = _open_help(qtbot)
    try:
        assert "<table" in help_window.content.document().toHtml()
    finally:
        window.close()


def test_help_content_stays_in_sync_with_docs() -> None:
    assert PACKAGED_GUIDE.read_bytes() == DOCS_GUIDE.read_bytes()


def test_help_falls_back_when_asset_missing(monkeypatch: object, tmp_path: Path) -> None:
    monkeypatch.setattr("qserialtool.ui.help_window.assets_dir", lambda: tmp_path)
    assert HelpWindow._load_help_text() == _FALLBACK_TEXT
