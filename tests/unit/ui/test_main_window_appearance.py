"""测试主窗口的字号、主题与显示偏好。"""

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QFont, QTextOption, QWheelEvent
from PySide6.QtWidgets import QApplication, QPlainTextEdit
from tests.fixtures.fakes import FakeClock, FakeTransport
from tests.fixtures.ui_helpers import (
    RecordingStore,
    build_window,
    build_window_with_store,
    current_tab,
)

from qserialtool.application import SessionManager
from qserialtool.domain import AppConfig, PortInfo, SerialConfig, SessionPreferences
from qserialtool.ui import MainWindow
from qserialtool.ui.theme_manager import DATA_FONT_PRESETS, data_font


def _checked_font_size(window: MainWindow) -> object:
    """返回“字号”子菜单当前勾选的档位值。"""
    return next(action for action in window.font_size_actions if action.isChecked()).data()


def _select_font_size(window: MainWindow, size: int) -> None:
    """勾选“字号”子菜单中的指定档位。"""
    action = next(action for action in window.font_size_actions if action.data() == size)
    action.setChecked(True)


def _checked_theme(window: MainWindow) -> object:
    """返回“主题”子菜单当前勾选的主题值。"""
    return next(action for action in window.theme_actions if action.isChecked()).data()


def _select_theme(window: MainWindow, theme: str) -> None:
    """勾选“主题”子菜单中的指定主题。"""
    action = next(action for action in window.theme_actions if action.data() == theme)
    action.setChecked(True)


def test_window_minimum_size_matches_layout_target(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)

    assert window.minimumSize().width() == 900
    assert window.minimumSize().height() == 600
    window.close()


def test_main_window_uses_app_icon(qtbot: object) -> None:
    window = build_window(qtbot, FakeTransport())

    try:
        assert not window.windowIcon().isNull()
    finally:
        window.close()


def test_data_panels_use_monospace_font(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    assert tab.receive_panel.output.font().styleHint() == QFont.StyleHint.Monospace
    assert tab.send_panel.editor.font().styleHint() == QFont.StyleHint.Monospace
    window.close()


def test_font_size_menu_scales_receive_and_send_panels(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        default_size = data_font().pointSize()
        assert tab.receive_panel.output.font().pointSize() == default_size

        _select_font_size(window, 18)
        assert tab.receive_panel.output.font().pointSize() == 18
        assert tab.send_panel.editor.font().pointSize() == 18

        _select_font_size(window, 0)
        assert tab.receive_panel.output.font().pointSize() == default_size
        assert tab.send_panel.editor.font().pointSize() == default_size
    finally:
        window.close()


def test_receive_wrap_toggle_controls_line_wrap(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        panel = tab.receive_panel
        assert panel.wrap_check.isChecked() is True
        assert panel.output.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
        assert panel.output.wordWrapMode() == QTextOption.WrapMode.WrapAnywhere
        assert tab.to_preferences().wrap_enabled is True

        tab.set_view_mode("terminal", persist=False)
        assert panel.wrap_check.isVisibleTo(tab)
        assert panel.output.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth

        panel.wrap_check.setChecked(False)
        assert panel.output.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap
        assert tab.to_preferences().wrap_enabled is False

        panel.wrap_check.setChecked(True)
        assert panel.output.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
        assert tab.to_preferences().wrap_enabled is True
    finally:
        tab.controller.close(force=True)
        window.close()


def test_wrap_enabled_restored_from_config(qtbot: object) -> None:
    transport = FakeTransport()
    manager = SessionManager(transport_factory=lambda: transport, clock=FakeClock())
    preferences = SessionPreferences(
        title="COM1",
        config=SerialConfig(port="COM1"),
        display_mode="text",
        show_timestamp=True,
        show_rx=True,
        show_tx=True,
        autoscroll=True,
        wrap_enabled=False,
    )
    config = AppConfig(
        schema_version=1,
        theme="system",
        window_geometry=None,
        window_state=None,
        active_session_index=0,
        sessions=(preferences,),
    )
    window = MainWindow(
        session_manager=manager,
        port_provider=lambda: (PortInfo(device="COM1"),),
        initial_config=config,
    )
    qtbot.addWidget(window)
    window.show()
    tab = current_tab(window)

    try:
        assert tab.receive_panel.wrap_check.isChecked() is False
        assert tab.receive_panel.output.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap
    finally:
        window.close()


def test_new_session_inherits_current_font_size(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)

    try:
        _select_font_size(window, 20)
        new_tab = window.new_session()

        assert new_tab.receive_panel.output.font().pointSize() == 20
        assert new_tab.send_panel.editor.font().pointSize() == 20
    finally:
        window.close()


def test_font_size_restored_from_config_and_persisted(qtbot: object) -> None:
    store = RecordingStore()
    transport = FakeTransport()
    manager = SessionManager(transport_factory=lambda: transport, clock=FakeClock())
    config = AppConfig(
        schema_version=1,
        theme="system",
        window_geometry=None,
        window_state=None,
        active_session_index=0,
        sessions=(),
        data_font_size=16,
    )
    window = MainWindow(
        session_manager=manager,
        port_provider=lambda: (PortInfo(device="COM1"),),
        config_store=store,
        initial_config=config,
    )
    qtbot.addWidget(window)
    window.show()
    tab = current_tab(window)

    try:
        assert _checked_font_size(window) == 16
        assert tab.receive_panel.output.font().pointSize() == 16

        _select_font_size(window, 24)
        window._save_config()

        assert store.saves[-1].data_font_size == 24
    finally:
        window.close()


def test_theme_change_keeps_data_font_size(qtbot: object) -> None:
    """样式表刷新会重新 polish 控件，数据区字号必须在主题切换后保持不变。"""
    window = build_window(qtbot, FakeTransport())
    tab = current_tab(window)

    try:
        _select_font_size(window, 18)
        assert tab.receive_panel.output.font().pointSize() == 18

        _select_theme(window, "dark")

        assert tab.receive_panel.output.font().pointSize() == 18
        assert tab.send_panel.editor.font().pointSize() == 18
    finally:
        window.close()


def _wheel(delta: int, modifiers: Qt.KeyboardModifier) -> QWheelEvent:
    position = QPointF(5, 5)
    return QWheelEvent(
        position,
        position,
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.MouseButton.NoButton,
        modifiers,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def test_font_shortcuts_step_through_presets(qtbot: object) -> None:
    transport = FakeTransport()
    store = RecordingStore()
    window = build_window_with_store(qtbot, transport, store)
    tab = current_tab(window)
    system_size = data_font().pointSize()
    zoom_in = [size for size in DATA_FONT_PRESETS if size > system_size]
    assert len(zoom_in) >= 2

    try:
        window.activateWindow()
        qtbot.waitUntil(window.isActiveWindow, timeout=2000)
        assert _checked_font_size(window) == 0

        qtbot.keyClick(window, Qt.Key.Key_Equal, Qt.KeyboardModifier.ControlModifier)
        assert _checked_font_size(window) == zoom_in[0]
        assert tab.receive_panel.output.font().pointSize() == zoom_in[0]
        assert tab.send_panel.editor.font().pointSize() == zoom_in[0]

        qtbot.keyClick(window, Qt.Key.Key_Equal, Qt.KeyboardModifier.ControlModifier)
        assert _checked_font_size(window) == zoom_in[1]

        qtbot.keyClick(window, Qt.Key.Key_Minus, Qt.KeyboardModifier.ControlModifier)
        assert _checked_font_size(window) == zoom_in[0]

        qtbot.keyClick(window, Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier)
        assert _checked_font_size(window) == zoom_in[1]

        window._save_config()
        assert store.saves[-1].data_font_size == zoom_in[1]

        qtbot.keyClick(window, Qt.Key.Key_0, Qt.KeyboardModifier.ControlModifier)
        assert _checked_font_size(window) == 0
        assert tab.receive_panel.output.font().pointSize() == system_size
    finally:
        tab.controller.close(force=True)
        window.close()


def test_ctrl_wheel_over_data_areas_zooms_font(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    system_size = data_font().pointSize()
    zoom_in = [size for size in DATA_FONT_PRESETS if size > system_size]
    assert len(zoom_in) >= 2

    try:
        QApplication.sendEvent(
            tab.receive_panel.output.viewport(),
            _wheel(120, Qt.KeyboardModifier.NoModifier),
        )
        assert _checked_font_size(window) == 0

        QApplication.sendEvent(
            tab.receive_panel.output.viewport(),
            _wheel(120, Qt.KeyboardModifier.ControlModifier),
        )
        assert _checked_font_size(window) == zoom_in[0]
        assert tab.send_panel.editor.font().pointSize() == zoom_in[0]

        QApplication.sendEvent(
            tab.send_panel.editor.viewport(),
            _wheel(120, Qt.KeyboardModifier.ControlModifier),
        )
        assert _checked_font_size(window) == zoom_in[1]

        QApplication.sendEvent(
            tab.send_panel.editor.viewport(),
            _wheel(-120, Qt.KeyboardModifier.ControlModifier),
        )
        assert _checked_font_size(window) == zoom_in[0]
        assert tab.receive_panel.output.font().pointSize() == zoom_in[0]
    finally:
        tab.controller.close(force=True)
        window.close()


def test_font_menu_lists_presets_and_zoom_actions(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)

    try:
        assert window.font_menu.title() == "字号"
        labels = [action.text() for action in window.font_menu.actions()]
        assert labels[0] == "跟随系统"
        assert labels[1 : 1 + len(DATA_FONT_PRESETS)] == [str(size) for size in DATA_FONT_PRESETS]
        assert labels[-3:] == ["放大", "缩小", "恢复默认"]
        presets = window.font_menu.actions()[: 1 + len(DATA_FONT_PRESETS)]
        assert all(action.isCheckable() for action in presets)
        assert window.font_zoom_in_action.shortcut().toString() == "Ctrl+="
        assert window.font_zoom_out_action.shortcut().toString() == "Ctrl+-"
        assert window.font_reset_action.shortcut().toString() == "Ctrl+0"
        assert any(action.menu() is window.font_menu for action in window.main_menu.actions())

        window.font_zoom_in_action.trigger()
        assert _checked_font_size(window) > 0

        window.font_reset_action.trigger()
        assert _checked_font_size(window) == 0
    finally:
        window.close()


def test_theme_menu_exposes_exclusive_choices(qtbot: object) -> None:
    """“主题”子菜单三项互斥，勾选即切换并持久化。"""
    store = RecordingStore()
    window = build_window_with_store(qtbot, FakeTransport(), store)

    try:
        themes = window.theme_menu.actions()
        assert [action.text() for action in themes] == ["跟随系统", "浅色", "深色"]
        assert all(action.isCheckable() for action in themes)
        assert _checked_theme(window) == "system"
        assert any(action.menu() is window.theme_menu for action in window.main_menu.actions())

        _select_theme(window, "dark")
        assert _checked_theme(window) == "dark"

        window._save_config()
        assert store.saves[-1].theme == "dark"
    finally:
        window.close()
