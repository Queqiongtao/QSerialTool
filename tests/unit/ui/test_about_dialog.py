"""测试关于对话框的菜单入口、内容与链接行为。"""

import platform

from PySide6.QtCore import QUrl, qVersion
from tests.fixtures.fakes import FakeClock, FakeTransport

from qserialtool import __version__
from qserialtool.application import SessionManager
from qserialtool.domain import PortInfo
from qserialtool.ui import AboutDialog, MainWindow
from qserialtool.ui.about_dialog import (
    _AUTHOR,
    _LICENSE_LABEL,
    _REPOSITORY_LABEL,
    _REPOSITORY_URL,
    _THIRD_PARTY_URL,
)


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


def _open_about(qtbot: object) -> tuple[MainWindow, AboutDialog]:
    window = _window(qtbot)
    window._show_about()
    dialog = window._about_dialog
    assert isinstance(dialog, AboutDialog)
    qtbot.addWidget(dialog)
    return window, dialog


def test_about_action_is_in_menu_after_help(qtbot: object) -> None:
    window = _window(qtbot)
    try:
        assert window.about_action.text() == "关于 QSerialTool"
        actions = window.main_menu.actions()
        assert actions[actions.index(window.help_action) + 1] is window.about_action
    finally:
        window.close()


def test_about_action_opens_single_reusable_dialog(qtbot: object) -> None:
    window, first = _open_about(qtbot)
    try:
        assert first.isVisible()
        window.about_action.trigger()
        assert window._about_dialog is first
    finally:
        window.close()


def test_about_dialog_shows_version_author_and_repository(qtbot: object) -> None:
    window, dialog = _open_about(qtbot)
    try:
        assert dialog.windowTitle() == "关于 QSerialTool"
        assert dialog.title_label.text() == "QSerialTool"
        assert dialog.title_label.font().bold() is True
        assert dialog.version_label.text() == f"版本：{__version__}"
        assert dialog.author_label.text() == f"作者：{_AUTHOR}"
        assert _REPOSITORY_LABEL in dialog.repository_label.text()
        assert dialog.repository_label.toolTip() == _REPOSITORY_URL
    finally:
        window.close()


def test_about_dialog_shows_environment_license_and_notices(qtbot: object) -> None:
    window, dialog = _open_about(qtbot)
    try:
        assert dialog.environment_label.text() == (
            f"运行环境：Python {platform.python_version()} · Qt {qVersion()}"
        )
        assert dialog.license_label.text() == f"版权：{_LICENSE_LABEL}"
        assert "第三方组件声明" in dialog.third_party_label.text()
        assert dialog.third_party_label.toolTip() == _THIRD_PARTY_URL
    finally:
        window.close()


def test_about_links_open_browser(qtbot: object, monkeypatch: object) -> None:
    opened: list[QUrl] = []

    class _FakeDesktopServices:
        @staticmethod
        def openUrl(url: QUrl) -> bool:
            opened.append(url)
            return True

    monkeypatch.setattr("qserialtool.ui.about_dialog.QDesktopServices", _FakeDesktopServices)
    window, dialog = _open_about(qtbot)
    try:
        dialog.repository_label.linkActivated.emit(_REPOSITORY_URL)
        dialog.third_party_label.linkActivated.emit(_THIRD_PARTY_URL)
        assert opened == [QUrl(_REPOSITORY_URL), QUrl(_THIRD_PARTY_URL)]
    finally:
        window.close()


def test_about_close_button_hides_dialog(qtbot: object) -> None:
    window, dialog = _open_about(qtbot)
    try:
        dialog.close_button.click()
        assert dialog.isVisible() is False
    finally:
        window.close()
