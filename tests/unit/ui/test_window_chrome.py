"""测试自定义标题行：窗口按钮行为、图标切换与拖动区域判定。"""

import ctypes
import sys

import pytest
from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QApplication, QWidget
from tests.fixtures.fakes import FakeClock, FakeTransport
from tests.fixtures.ui_helpers import build_window

from qserialtool.application import SessionManager
from qserialtool.domain import PortInfo
from qserialtool.ui import MainWindow, window_chrome
from qserialtool.ui.theme_manager import apply_theme
from qserialtool.ui.window_chrome import (
    WINDOW_BUTTON_WIDTH_PX,
    WindowButtons,
    apply_window_theme,
    build_window_menu,
    handle_native_event,
    is_title_drag_point,
    resize_edges_for,
    uses_custom_title_bar,
    uses_native_chrome,
)

_WINDOWS = sys.platform.startswith("win")
_LINUX = sys.platform.startswith("linux")


def _buttons(window: object) -> WindowButtons:
    buttons = getattr(window, "window_buttons", None)
    if buttons is None:
        pytest.skip("窗口按钮仅在 Windows/Linux 桌面平台装配")
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
        pytest.skip("窗口按钮仅在 Windows/Linux 桌面平台装配")
    assert uses_native_chrome() is (QApplication.platformName() != "offscreen")


def test_apply_window_theme_tolerates_offscreen_and_real_handles(qtbot: object) -> None:
    """离屏平台句柄无效时必须静默降级；真实 Windows 句柄能完整走通。"""
    transport = FakeTransport()
    window = build_window(qtbot, transport)

    try:
        # 深浅主题来回应用必须安全返回：旧属性 id、圆角偏好不被支持时应静默降级。
        apply_window_theme(window, is_dark=True)
        apply_window_theme(window, is_dark=False)
        apply_window_theme(window, is_dark=True)
    finally:
        window.close()


def test_apply_window_theme_sets_border_color_from_theme(monkeypatch: object) -> None:
    """边框描边颜色必须跟随主题窗口底色，消除系统默认的浅色细线。"""
    calls: list[tuple[int, int]] = []

    class _FakeApi:
        def dwm_set_window_attribute(
            self, hwnd: int, attribute: int, pointer: object, size: int
        ) -> int:
            value = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_int))[0]
            calls.append((attribute, value))
            return 0

    class _FakeWindow:
        def winId(self) -> int:
            return 4242

    monkeypatch.setattr(window_chrome, "_WINDOWS", True)
    monkeypatch.setattr(window_chrome, "_api", _FakeApi)

    window_chrome.apply_window_theme(_FakeWindow(), is_dark=True)
    window_chrome.apply_window_theme(_FakeWindow(), is_dark=False)

    # 属性 20 沉浸式深色、33 圆角偏好、34 描边颜色（主题窗口底色的 COLORREF）。
    assert calls == [
        (20, 1),
        (33, 2),
        (34, 0x211D1B),  # 深色窗口底色 #1B1D21。
        (20, 0),
        (33, 2),
        (34, 0xF6F4F3),  # 浅色窗口底色 #F3F4F6。
    ]


def _read_dwm_dword(window: QWidget, attribute: int) -> int | None:
    """回读 DWM DWORD 属性；系统不支持回读该属性时返回 None。"""
    value = ctypes.c_int(0)
    result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        ctypes.c_void_p(int(window.winId())),
        ctypes.c_uint(attribute),
        ctypes.byref(value),
        ctypes.sizeof(value),
    )
    return value.value if result == 0 else None


def test_theme_switch_keeps_immersive_dark_attr_in_sync(qtbot: object) -> None:
    """回归：切换主题后原生边框的沉浸式深色属性必须跟随应用主题。

    此前缺陷：应用未向 Qt 声明配色方案，平台插件按系统配色（浅色）异步
    重置该属性，深色主题下窗口顶部残存浅色缩放边框。
    """
    if not _WINDOWS or not uses_native_chrome():
        pytest.skip("需要 Windows 桌面平台的真实窗口句柄")
    app = QApplication.instance()
    assert app is not None
    transport = FakeTransport()
    window = build_window(qtbot, transport)

    try:
        if _read_dwm_dword(window, 20) is None:
            pytest.skip("当前系统不支持回读沉浸式深色属性")

        apply_theme(app, "dark")
        qtbot.waitUntil(lambda: _read_dwm_dword(window, 20) == 1, timeout=2000)
        apply_theme(app, "light")
        qtbot.waitUntil(lambda: _read_dwm_dword(window, 20) == 0, timeout=2000)
    finally:
        apply_theme(app, "system")
        window.close()


def test_apply_window_theme_skips_native_calls_on_non_windows(
    monkeypatch: object, qtbot: object
) -> None:
    monkeypatch.setattr(window_chrome, "_WINDOWS", False)
    # 未创建原生窗口的控件：非 Windows 平台不应触碰 winId()。
    naked = QWidget()
    try:
        window_chrome.apply_window_theme(naked, is_dark=True)
    finally:
        naked.deleteLater()


def test_keep_window_hidden_suppresses_early_native_visibility(qtbot: object) -> None:
    """回归：构造期间被提前显示的原生窗口必须重新保持隐藏。

    部分 Windows 启动路径上主窗口会在构造中途（默认尺寸、系统标题栏）提前
    可见约一秒再跳变到保存状态，观感是“先小窗口、再放大”；keep_window_hidden
    负责把第一个可见帧留给应用自己的 show()。
    """
    if not _WINDOWS or not uses_native_chrome():
        pytest.skip("需要 Windows 桌面平台的真实窗口句柄")
    transport = FakeTransport()
    manager = SessionManager(transport_factory=lambda: transport, clock=FakeClock())
    window = MainWindow(
        session_manager=manager,
        port_provider=lambda: (PortInfo(device="COM1"),),
    )
    qtbot.addWidget(window)
    user32 = ctypes.windll.user32
    try:
        hwnd = ctypes.c_void_p(int(window.winId()))
        user32.ShowWindow(hwnd, 5)  # SW_SHOW：模拟构造期间被系统提前显示
        assert user32.IsWindowVisible(hwnd)

        window_chrome.keep_window_hidden(window)
        assert not user32.IsWindowVisible(hwnd)

        window.show()
        assert user32.IsWindowVisible(hwnd)
        # 窗口已被应用显示后，本函数不得再触碰原生可见性。
        window_chrome.keep_window_hidden(window)
        assert user32.IsWindowVisible(hwnd)
    finally:
        window.close()


def test_keep_window_hidden_skips_native_calls_on_non_windows(
    monkeypatch: object, qtbot: object
) -> None:
    monkeypatch.setattr(window_chrome, "_WINDOWS", False)
    # 未创建原生窗口的控件：非 Windows 平台不应触碰 winId()。
    naked = QWidget()
    try:
        window_chrome.keep_window_hidden(naked)
    finally:
        naked.deleteLater()


def test_resize_edges_for_detects_edges_corners_and_interior() -> None:
    size = QSize(200, 120)
    assert resize_edges_for(QPoint(3, 60), size) == Qt.Edge.LeftEdge
    assert resize_edges_for(QPoint(197, 60), size) == Qt.Edge.RightEdge
    assert resize_edges_for(QPoint(100, 2), size) == Qt.Edge.TopEdge
    assert resize_edges_for(QPoint(100, 119), size) == Qt.Edge.BottomEdge
    assert resize_edges_for(QPoint(0, 0), size) == (Qt.Edge.LeftEdge | Qt.Edge.TopEdge)
    assert resize_edges_for(QPoint(50, 50), size) is None


def test_resize_cursor_matches_corners_and_edges() -> None:
    assert (
        window_chrome._resize_cursor(Qt.Edge.LeftEdge | Qt.Edge.TopEdge)
        is Qt.CursorShape.SizeFDiagCursor
    )
    assert (
        window_chrome._resize_cursor(Qt.Edge.RightEdge | Qt.Edge.TopEdge)
        is Qt.CursorShape.SizeBDiagCursor
    )
    assert window_chrome._resize_cursor(Qt.Edge.RightEdge) is Qt.CursorShape.SizeHorCursor
    assert window_chrome._resize_cursor(Qt.Edge.BottomEdge) is Qt.CursorShape.SizeVerCursor


def test_uses_custom_title_bar_platform_matrix(monkeypatch: object) -> None:
    monkeypatch.setattr(window_chrome, "_WINDOWS", True)
    monkeypatch.setattr(window_chrome, "_platform_name", lambda: "")
    assert uses_custom_title_bar() is True
    monkeypatch.setattr(window_chrome, "_platform_name", lambda: "offscreen")
    assert uses_custom_title_bar() is False

    monkeypatch.setattr(window_chrome, "_WINDOWS", False)
    monkeypatch.setattr(window_chrome.sys, "platform", "linux")
    monkeypatch.setattr(window_chrome, "_platform_name", lambda: "xcb")
    assert uses_custom_title_bar() is True
    monkeypatch.setattr(window_chrome, "_platform_name", lambda: "wayland")
    assert uses_custom_title_bar() is True
    monkeypatch.setattr(window_chrome, "_platform_name", lambda: "minimal")
    assert uses_custom_title_bar() is False


def test_show_window_menu_prefers_native_x11(qapp: QApplication, monkeypatch: object) -> None:
    window = QWidget()
    native_calls: list[tuple[QWidget, QPoint]] = []
    fallback_calls: list[QWidget] = []
    try:
        monkeypatch.setattr(
            window_chrome,
            "_send_x11_window_menu",
            lambda w, pos: native_calls.append((w, pos)) or True,
        )
        monkeypatch.setattr(window_chrome, "build_window_menu", fallback_calls.append)
        pos = QPoint(10, 20)
        window_chrome.show_window_menu(window, pos)
        assert native_calls == [(window, pos)]
        assert fallback_calls == []
    finally:
        window.deleteLater()


def test_show_window_menu_falls_back_to_own_menu(qapp: QApplication, monkeypatch: object) -> None:
    window = QWidget()
    executed: list[QPoint] = []

    class _FakeMenu:
        def exec(self, pos: QPoint) -> None:
            executed.append(pos)

    try:
        monkeypatch.setattr(window_chrome, "_send_x11_window_menu", lambda w, pos: False)
        monkeypatch.setattr(window_chrome, "build_window_menu", lambda w: _FakeMenu())
        pos = QPoint(3, 4)
        window_chrome.show_window_menu(window, pos)
        assert executed == [pos]
    finally:
        window.deleteLater()


def test_build_window_menu_actions(qapp: QApplication, qtbot: object) -> None:
    window = QWidget()
    try:
        menu = build_window_menu(window)
        titles = [action.text() for action in menu.actions()]
        assert titles[0] == "最小化"
        assert titles[1] in {"最大化", "还原"}
        assert titles[2] == "关闭"
        menu.deleteLater()
    finally:
        window.deleteLater()


@pytest.mark.skipif(not _LINUX, reason="Linux 专属无边框标题栏实现")
def test_enable_linux_custom_title_bar_sets_flag_and_filters(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    try:
        window_chrome.enable_linux_custom_title_bar(window)
        assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert window.findChild(window_chrome._LinuxTitleBarFilter) is not None
        assert window.findChild(window_chrome._LinuxResizeFilter) is not None
    finally:
        window.close()


@pytest.mark.skipif(not _LINUX, reason="Linux 专属无边框标题栏实现")
def test_linux_title_bar_filter_opens_menu_on_blank_context_click(
    qtbot: object, monkeypatch: object
) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    calls: list[tuple[QWidget, QPoint]] = []
    try:
        monkeypatch.setattr(
            window_chrome, "show_window_menu", lambda w, pos: calls.append((w, pos))
        )
        window_chrome.enable_linux_custom_title_bar(window)
        tab_bar = window.tabs.tabBar()
        pos = QPoint(tab_bar.width() - 12, tab_bar.height() // 2)
        assert tab_bar.tabAt(pos) < 0
        global_pos = tab_bar.mapToGlobal(pos)
        event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, pos, global_pos)
        QApplication.sendEvent(tab_bar, event)
        assert calls == [(window, global_pos)]
    finally:
        window.close()
