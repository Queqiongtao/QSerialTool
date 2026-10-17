"""测试动作图标资源加载与状态相关按钮的图标切换。"""

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QImage
from PySide6.QtWidgets import QAbstractButton, QApplication, QMessageBox
from tests.fixtures.fakes import FakeTransport
from tests.fixtures.ui_helpers import build_window, connect_session, current_tab

from qserialtool.domain import SessionState
from qserialtool.ui.icons import ACTION_ICON_PX, svg_icon
from qserialtool.ui.style_sheet import assets_dir

# 动作图标清单：新增图标时必须同步，防止资源改名或漏打包后在界面上静默变空。
_ACTION_ICONS = (
    "pause",
    "play",
    "eraser",
    "terminal",
    "split",
    "sidebar",
    "timer",
    "stop",
    "refresh",
    "sliders",
    "send",
    "send-disabled",
    "plug",
    "unplug",
    "unplug-disabled",
    "close",
    "close-hover",
    "plus",
    "window-minimize",
    "window-maximize",
    "window-restore",
    "window-close",
    "window-close-active",
)


def _image(icon: QIcon) -> QImage:
    return icon.pixmap(ACTION_ICON_PX, ACTION_ICON_PX).toImage()


def _button_image(button: QAbstractButton) -> QImage:
    return _image(button.icon())


def test_action_icon_files_exist() -> None:
    """图标文件必须真实存在，防止打包清单漏掉新增资源。"""
    for name in _ACTION_ICONS:
        assert (assets_dir() / f"{name}.svg").is_file(), name


def test_action_icons_load(qapp: QApplication) -> None:
    """全部动作图标资源必须存在且能渲染出非空图像。"""
    for name in _ACTION_ICONS:
        icon = svg_icon(name)
        assert not icon.isNull(), name
        assert not _image(icon).isNull(), name


def test_missing_action_icon_is_empty(qapp: QApplication) -> None:
    """资源缺失时返回空图标，界面不抛错（与 app_icon 的行为一致）。"""
    assert svg_icon("no-such-action").isNull()


def test_pause_button_icon_swaps_with_state(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    panel = tab.receive_panel
    try:
        paused_image = _button_image(panel.pause_button)
        panel.pause_button.setChecked(True)
        assert panel.pause_button.text() == "继续"
        assert _button_image(panel.pause_button) != paused_image
        assert _button_image(panel.pause_button) == _image(svg_icon("play"))

        panel.pause_button.setChecked(False)
        assert panel.pause_button.text() == "暂停"
        assert _button_image(panel.pause_button) == paused_image
    finally:
        window.close()


def test_periodic_button_icon_swaps_with_state(qtbot: object, monkeypatch: object) -> None:
    # 已连接会话关闭窗口时会弹退出确认，测试内直接选择“是”避免阻塞。
    monkeypatch.setattr(  # type: ignore[attr-defined]
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    panel = tab.send_panel
    try:
        connect_session(qtbot, tab)
        started_image = _button_image(panel.periodic_button)
        panel.editor.setPlainText("AT")

        panel.periodic_button.setChecked(True)
        assert panel.periodic_button.text() == "停止周期"
        assert _button_image(panel.periodic_button) != started_image
        assert _button_image(panel.periodic_button) == _image(svg_icon("stop"))

        panel.periodic_button.setChecked(False)
        assert panel.periodic_button.text() == "开始周期"
        assert _button_image(panel.periodic_button) == started_image
    finally:
        window.close()


def test_view_toggle_icon_swaps_with_state(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    button = window.view_toggle_button
    try:
        split_image = _button_image(button)
        assert split_image == _image(svg_icon("terminal"))

        button.setChecked(True)
        assert button.text() == "分栏"
        assert _button_image(button) == _image(svg_icon("split"))

        button.setChecked(False)
        assert button.text() == "终端"
        assert _button_image(button) == split_image
    finally:
        window.close()


def test_connect_button_icon_tracks_session_state(qtbot: object, monkeypatch: object) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    panel = tab.connection_panel
    try:
        plug_image = _image(svg_icon("plug"))
        assert _button_image(panel.connect_button) == plug_image

        connect_session(qtbot, tab)
        unplug_image = _image(svg_icon("unplug"))
        assert panel.connect_button.text() == "断开"
        assert _button_image(panel.connect_button) == unplug_image

        panel.apply_snapshot(replace(tab.controller.snapshot, state=SessionState.DISCONNECTING))
        assert panel.connect_button.text() == "正在断开"
        assert not panel.connect_button.isEnabled()
        assert _button_image(panel.connect_button) == _image(svg_icon("unplug-disabled"))
    finally:
        window.close()


def test_send_button_icon_tracks_connection(qtbot: object, monkeypatch: object) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    panel = tab.send_panel
    try:
        assert _button_image(panel.send_button) == _image(svg_icon("send-disabled"))

        connect_session(qtbot, tab)
        assert _button_image(panel.send_button) == _image(svg_icon("send"))
    finally:
        window.close()


def test_tool_buttons_show_icon_beside_text(qtbot: object) -> None:
    """顶部侧栏、视图切换和终端发送设置必须声明“图标 + 文字”，避免退化为纯图标。"""
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    try:
        assert (
            window.sidebar_toggle_button.toolButtonStyle()
            is Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        assert (
            window.view_toggle_button.toolButtonStyle()
            is Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        assert (
            tab.send_settings_button.toolButtonStyle()
            is Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
    finally:
        window.close()
