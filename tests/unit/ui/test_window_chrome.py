"""测试自定义标题行：窗口按钮行为、图标切换与拖动区域判定。"""

import sys

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication
from tests.fixtures.fakes import FakeTransport
from tests.fixtures.ui_helpers import build_window

from qserialtool.ui.window_chrome import (
    WINDOW_BUTTON_WIDTH_PX,
    WindowButtons,
    handle_native_event,
    is_title_drag_point,
    uses_native_chrome,
)

_WINDOWS = sys.platform.startswith("win")


def _buttons(window: object) -> WindowButtons:
    buttons = getattr(window, "window_buttons", None)
    if buttons is None:
        pytest.skip("自定义标题栏仅在 Windows 上提供")
    return buttons


def test_window_buttons_lay_out_in_single_row_header(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)

    try:
        buttons = _buttons(window)
        corner = window.tabs.cornerWidget(Qt.Corner.TopRightCorner)
        assert buttons.objectName() == "windowControls"
        assert corner is not None
        assert buttons.parentWidget() is corner
        assert buttons.isVisible()

        assert buttons.minimize_button.objectName() == "windowMinButton"
        assert buttons.maximize_button.objectName() == "windowMaxButton"
        assert buttons.close_button.objectName() == "windowCloseButton"
        assert buttons.minimize_button.toolTip() == "最小化"
        assert buttons.maximize_button.toolTip() == "最大化"
        assert buttons.close_button.toolTip() == "关闭"
        for button in (
            buttons.minimize_button,
            buttons.maximize_button,
            buttons.close_button,
        ):
            assert button.width() == WINDOW_BUTTON_WIDTH_PX
            assert button.isVisible()
    finally:
        window.close()


def test_minimize_button_minimizes_window(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)

    try:
        buttons = _buttons(window)
        qtbot.mouseClick(buttons.minimize_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(window.isMinimized, timeout=2000)
    finally:
        window.showNormal()
        window.close()


def test_maximize_button_swaps_icon_and_tooltip(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)

    try:
        buttons = _buttons(window)
        maximize = buttons.maximize_button
        icon_size = maximize.iconSize()
        initial_icon = maximize.icon().pixmap(icon_size).toImage()
        assert maximize.toolTip() == "最大化"

        qtbot.mouseClick(maximize, Qt.MouseButton.LeftButton)
        assert window.isMaximized()
        assert maximize.toolTip() == "还原"
        assert maximize.icon().pixmap(icon_size).toImage() != initial_icon

        qtbot.mouseClick(maximize, Qt.MouseButton.LeftButton)
        assert not window.isMaximized()
        assert maximize.toolTip() == "最大化"

        # 外部状态变化（双击标题行、Win+↑ 等）同样同步图标与提示。
        window.showMaximized()
        assert maximize.toolTip() == "还原"
    finally:
        window.showNormal()
        window.close()


def test_close_button_closes_window(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)

    try:
        buttons = _buttons(window)
        qtbot.mouseClick(buttons.close_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: not window.isVisible(), timeout=2000)
    finally:
        window.close()


def test_tab_strip_drag_region_detection(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)

    try:
        bar = window.tab_bar
        new_tab_button = window.new_tab_button
        assert bar.count() == 1
        assert new_tab_button.isVisible()

        # 标签行空白处（最后一个标签右侧）→ 应作为 HTCAPTION 拖动区域。
        strip_point = QPoint(new_tab_button.geometry().right() + 12, bar.height() // 2)
        assert bar.tabAt(strip_point) == -1
        assert window.childAt(bar.mapTo(window, strip_point)) is bar
        assert (
            is_title_drag_point(
                window.childAt(bar.mapTo(window, strip_point)),
                tab_bar=bar,
                pos=strip_point,
            )
            is True
        )

        # 标签本身 → 正常点击。
        tab_point = bar.tabRect(0).center()
        assert (
            is_title_drag_point(
                window.childAt(bar.mapTo(window, tab_point)),
                tab_bar=bar,
                pos=tab_point,
            )
            is False
        )

        # “+”新建按钮 → 正常点击。
        button_point = new_tab_button.geometry().center()
        assert window.childAt(bar.mapTo(window, button_point)) is new_tab_button
        assert (
            is_title_drag_point(
                window.childAt(bar.mapTo(window, button_point)),
                tab_bar=bar,
                pos=button_point,
            )
            is False
        )
    finally:
        window.close()


def test_native_event_hook_ignores_foreign_messages(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)

    try:
        assert handle_native_event(window, b"windows_dispatcher_MSG", 0) is None
    finally:
        window.close()


def test_native_chrome_follows_platform_policy(qapp: object) -> None:
    if not _WINDOWS:
        pytest.skip("自定义标题栏仅在 Windows 上提供")
    assert uses_native_chrome() is (QApplication.platformName() != "offscreen")
