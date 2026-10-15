"""测试主窗口、标签组织和全局显示偏好。"""

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import (
    QContextMenuEvent,
    QFont,
    QMouseEvent,
    QTextOption,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QInputDialog,
    QLineEdit,
    QMenuBar,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QToolBar,
)
from shiboken6 import isValid
from tests.fixtures.fakes import FakeClock, FakeTransport
from tests.fixtures.ui_helpers import (
    RecordingStore,
    build_window,
    build_window_with_store,
    connect_session,
    current_tab,
    disconnect_session,
)

from qserialtool.application import MAX_SESSION_TITLE_LENGTH, SessionManager
from qserialtool.domain import (
    DEFAULT_LINE_ENDING,
    AppConfig,
    PortInfo,
    SerialConfig,
    SessionPreferences,
    SessionState,
)
from qserialtool.ui import MainWindow, data_colors
from qserialtool.ui.theme_manager import (
    DATA_FONT_PRESETS,
    data_font,
)


def test_main_window_connects_sends_receives_and_disconnects(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        assert tab.connection_panel.baud_combo.currentText() == "9600"
        assert not tab.connection_panel.port_combo.isEnabled()
        assert tab.send_panel.send_button.isEnabled()

        tab.send_panel.editor.setPlainText("ping")
        newline_index = tab.send_panel.newline_combo.findData("lf")
        tab.send_panel.newline_combo.setCurrentIndex(newline_index)
        qtbot.mouseClick(tab.send_panel.send_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: transport.writes == [b"ping\n"], timeout=2000)

        transport.push_read(b"pong")
        qtbot.waitUntil(lambda: "pong" in tab.receive_panel.output.toPlainText(), timeout=2000)

        hex_index = tab.receive_panel.mode_combo.findData("hex")
        tab.receive_panel.mode_combo.setCurrentIndex(hex_index)
        assert "70 6F 6E 67" in tab.receive_panel.output.toPlainText()

        disconnect_session(qtbot, tab)
        assert transport.close_count == 1
    finally:
        tab.controller.close(force=True)
        window.close()


def test_main_window_creates_multiple_independent_tabs(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    first = current_tab(window)

    second = window.new_session()

    assert window.tabs.count() == 2
    assert second.controller.session_id != first.controller.session_id
    assert second.controller.state is not SessionState.CONNECTED
    assert second.send_panel.line_ending == DEFAULT_LINE_ENDING == "lf"
    window.close()


def test_main_window_validates_invalid_baud_and_hex(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(str(args[2])),
    )

    tab.connection_panel.baud_combo.setEditText("invalid")
    qtbot.mouseClick(tab.connection_panel.connect_button, Qt.MouseButton.LeftButton)
    assert tab.controller.state is SessionState.DISCONNECTED
    assert warnings == ["波特率必须是正整数。"]

    connect_session(qtbot, tab)
    hex_index = tab.send_panel.mode_combo.findData("hex")
    tab.send_panel.mode_combo.setCurrentIndex(hex_index)
    tab.send_panel.editor.setPlainText("ZZ")
    qtbot.mouseClick(tab.send_panel.send_button, Qt.MouseButton.LeftButton)
    assert warnings[-1] == "HEX 数据包含非法字符：'Z'。"

    disconnect_session(qtbot, tab)
    window.close()


def test_main_window_requires_confirmation_to_close_active_tab(
    qtbot: object,
    monkeypatch: object,
) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    connect_session(qtbot, tab)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    window._close_tab(0)

    assert window.tabs.count() == 0
    assert tab.controller.state is SessionState.CLOSED
    assert transport.close_count == 1
    window.close()


def test_close_tab_schedules_widget_destruction(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    window._close_tab(0)
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    assert window.tabs.count() == 0
    assert not isValid(tab)
    window.close()


def test_snapshot_fanout_skips_unchanged_panels(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    calls = {"connection": 0, "log": 0}
    original_connection = tab.connection_panel.apply_snapshot
    original_log = tab.log_panel.apply_snapshot

    def counting_connection(snapshot: object) -> None:
        calls["connection"] += 1
        original_connection(snapshot)

    def counting_log(snapshot: object) -> None:
        calls["log"] += 1
        original_log(snapshot)

    monkeypatch.setattr(tab.connection_panel, "apply_snapshot", counting_connection)
    monkeypatch.setattr(tab.log_panel, "apply_snapshot", counting_log)
    try:
        connect_session(qtbot, tab)
        baseline = dict(calls)
        assert baseline["connection"] > 0
        assert baseline["log"] > 0

        transport.push_read(b"payload")
        qtbot.waitUntil(lambda: "RX 7 B" in tab.status_label.text(), timeout=2000)

        assert calls == baseline

        disconnect_session(qtbot, tab)
        qtbot.waitUntil(
            lambda: calls["connection"] > baseline["connection"],
            timeout=2000,
        )
        assert calls["log"] > baseline["log"]
    finally:
        window.close()


def test_session_tab_places_settings_in_left_sidebar_and_toggles(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    assert tab.layout_splitter.widget(0) is tab.sidebar
    assert tab.layout_splitter.widget(1) is tab.main_content
    assert isinstance(tab.sidebar, QScrollArea)
    assert tab.sidebar.widget() is tab.sidebar_content
    assert tab.connection_panel.parentWidget() is tab.sidebar_content
    assert tab.log_panel.parentWidget() is tab.sidebar_content
    assert tab.sidebar_toggle_button.parentWidget() is tab.receive_panel
    assert tab.receive_send_splitter.widget(0) is tab.receive_panel
    assert tab.receive_send_splitter.widget(1) is tab.send_panel
    assert tab.sidebar.isVisible()

    qtbot.mouseClick(tab.sidebar_toggle_button, Qt.MouseButton.LeftButton)
    assert not tab.sidebar.isVisible()
    assert tab.sidebar_toggle_button.text() == "展开设置"

    qtbot.mouseClick(tab.sidebar_toggle_button, Qt.MouseButton.LeftButton)
    assert tab.sidebar.isVisible()
    assert tab.sidebar_toggle_button.text() == "收起设置"
    assert tab.layout_state()[0] is True
    window.close()


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


def test_font_size_combo_scales_receive_and_send_panels(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        default_size = data_font().pointSize()
        assert tab.receive_panel.output.font().pointSize() == default_size

        window.font_combo.setCurrentIndex(window.font_combo.findData(18))
        assert tab.receive_panel.output.font().pointSize() == 18
        assert tab.send_panel.editor.font().pointSize() == 18

        window.font_combo.setCurrentIndex(window.font_combo.findData(0))
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
        window.font_combo.setCurrentIndex(window.font_combo.findData(20))
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
        assert window.font_combo.currentData() == 16
        assert tab.receive_panel.output.font().pointSize() == 16

        window.font_combo.setCurrentIndex(window.font_combo.findData(24))
        window._save_config()

        assert store.saves[-1].data_font_size == 24
    finally:
        window.close()


def test_theme_change_keeps_data_font_size(qtbot: object) -> None:
    """样式表刷新会重新 polish 控件，数据区字号必须在主题切换后保持不变。"""
    window = build_window(qtbot, FakeTransport())
    tab = current_tab(window)

    try:
        window.font_combo.setCurrentIndex(window.font_combo.findData(18))
        assert tab.receive_panel.output.font().pointSize() == 18

        window.theme_combo.setCurrentIndex(window.theme_combo.findData("dark"))

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
        assert window.font_combo.currentData() == 0

        qtbot.keyClick(window, Qt.Key.Key_Equal, Qt.KeyboardModifier.ControlModifier)
        assert window.font_combo.currentData() == zoom_in[0]
        assert tab.receive_panel.output.font().pointSize() == zoom_in[0]
        assert tab.send_panel.editor.font().pointSize() == zoom_in[0]

        qtbot.keyClick(window, Qt.Key.Key_Equal, Qt.KeyboardModifier.ControlModifier)
        assert window.font_combo.currentData() == zoom_in[1]

        qtbot.keyClick(window, Qt.Key.Key_Minus, Qt.KeyboardModifier.ControlModifier)
        assert window.font_combo.currentData() == zoom_in[0]

        qtbot.keyClick(window, Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier)
        assert window.font_combo.currentData() == zoom_in[1]

        window._save_config()
        assert store.saves[-1].data_font_size == zoom_in[1]

        qtbot.keyClick(window, Qt.Key.Key_0, Qt.KeyboardModifier.ControlModifier)
        assert window.font_combo.currentData() == 0
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
        assert window.font_combo.currentData() == 0

        QApplication.sendEvent(
            tab.receive_panel.output.viewport(),
            _wheel(120, Qt.KeyboardModifier.ControlModifier),
        )
        assert window.font_combo.currentData() == zoom_in[0]
        assert tab.send_panel.editor.font().pointSize() == zoom_in[0]

        QApplication.sendEvent(
            tab.send_panel.editor.viewport(),
            _wheel(120, Qt.KeyboardModifier.ControlModifier),
        )
        assert window.font_combo.currentData() == zoom_in[1]

        QApplication.sendEvent(
            tab.send_panel.editor.viewport(),
            _wheel(-120, Qt.KeyboardModifier.ControlModifier),
        )
        assert window.font_combo.currentData() == zoom_in[0]
        assert tab.receive_panel.output.font().pointSize() == zoom_in[0]
    finally:
        tab.controller.close(force=True)
        window.close()


def test_font_menu_exposes_zoom_actions(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)

    try:
        assert window.font_menu.title() == "字号"
        assert [action.text() for action in window.font_menu.actions()] == [
            "放大",
            "缩小",
            "恢复默认",
        ]
        assert window.font_zoom_in_action.shortcut().toString() == "Ctrl+="
        assert window.font_zoom_out_action.shortcut().toString() == "Ctrl+-"
        assert window.font_reset_action.shortcut().toString() == "Ctrl+0"
        assert any(action.menu() is window.font_menu for action in window.main_menu.actions())

        window.font_zoom_in_action.trigger()
        assert window.font_combo.currentData() > 0

        window.font_reset_action.trigger()
        assert window.font_combo.currentData() == 0
    finally:
        window.close()


def test_send_panel_and_content_fit_narrow_window(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    # 上限跟随 QSS 控件内边距：900px 窗口下发送区可用宽度约 600px，仍留足余量。
    assert tab.send_panel.minimumSizeHint().width() <= 560

    window.resize(900, 600)
    receive_panel = tab.receive_panel
    qtbot.waitUntil(lambda: bool(receive_panel._header_overflow.folded_widgets()), timeout=2000)
    for widget in (receive_panel.pause_button, receive_panel.clear_button, tab.view_toggle_button):
        assert widget.isVisibleTo(tab)
        assert widget.geometry().right() <= receive_panel.width()
    assert receive_panel._header_overflow.button.geometry().right() <= receive_panel.width()
    window.close()


def test_new_session_action_and_tab_button_create_sessions(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)

    action = next(item for item in window.main_menu.actions() if item.text() == "新建会话")
    action.trigger()
    assert window.tabs.count() == 2

    qtbot.mouseClick(window.new_tab_button, Qt.MouseButton.LeftButton)
    assert window.tabs.count() == 3
    window.close()


def test_main_window_uses_single_row_header(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)

    assert window.findChildren(QToolBar) == []
    assert window.findChildren(QMenuBar) == []

    corner = window.tabs.cornerWidget(Qt.Corner.TopRightCorner)
    assert corner is not None
    assert window.theme_combo.parentWidget() is corner
    assert window.font_combo.parentWidget() is corner
    assert window.new_tab_button.parentWidget() is corner
    assert window.menu_button.parentWidget() is corner
    assert window.theme_combo.isVisible()
    assert window.font_combo.isVisible()
    assert window.new_tab_button.isVisible()
    assert window.menu_button.isVisible()
    window.close()


def test_header_actions_keep_shortcuts_without_menu_bar(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    shortcuts = {action.text(): action.shortcut().toString() for action in window.actions()}

    assert shortcuts["新建会话"] == "Ctrl+T"
    assert shortcuts["关闭当前会话"] == "Ctrl+W"
    assert shortcuts["退出"] == "Ctrl+Q"

    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow, timeout=2000)
    qtbot.keyClick(window, Qt.Key.Key_T, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: window.tabs.count() == 2, timeout=2000)
    window.close()


def test_status_indicator_tracks_session_state(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    try:
        assert data_colors().idle in tab.state_indicator.styleSheet()
        connect_session(qtbot, tab)
        assert data_colors().connected in tab.state_indicator.styleSheet()
    finally:
        disconnect_session(qtbot, tab)
        window.close()


def test_tab_double_click_renames_session(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    store = RecordingStore()
    window = build_window_with_store(qtbot, transport, store)
    tab = current_tab(window)
    monkeypatch.setattr(MainWindow, "_ask_session_title", lambda self, initial: "水泵")

    rect = window.tabs.tabBar().tabRect(0)
    qtbot.mouseDClick(window.tabs.tabBar(), Qt.MouseButton.LeftButton, pos=rect.center())

    try:
        assert tab.controller.title == "水泵"
        qtbot.waitUntil(lambda: window.tabs.tabText(0) == "水泵", timeout=2000)
        assert window.tabs.tabToolTip(0) == "水泵"

        window._save_timer.stop()
        window._save_config()
        assert store.saves
        assert store.saves[-1].sessions[0].title == "水泵"
    finally:
        window.close()


def test_tab_context_menu_renames_clicked_tab(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    first = current_tab(window)
    second = window.new_session()
    monkeypatch.setattr(MainWindow, "_ask_session_title", lambda self, initial: "第二个")

    menu = window._build_tab_menu(1)
    action = next(item for item in menu.actions() if item.text() == "重命名…")
    action.trigger()

    try:
        assert second.controller.title == "第二个"
        qtbot.waitUntil(lambda: window.tabs.tabText(1) == "第二个", timeout=2000)
        assert first.controller.title == "会话 1"
        assert window.tabs.tabText(0) == "会话 1"
    finally:
        window.close()


def test_tab_rename_cancel_keeps_title(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    monkeypatch.setattr(MainWindow, "_ask_session_title", lambda self, initial: None)

    window._prompt_rename(0)

    try:
        assert tab.controller.title == "会话 1"
        assert window.tabs.tabText(0) == "会话 1"
    finally:
        window.close()


def test_tab_bar_context_menu_event_opens_menu(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    window.new_session()
    bar = window.tabs.tabBar()
    bar.setCurrentIndex(0)
    opened: list[tuple[int, tuple[int, int]]] = []
    monkeypatch.setattr(
        MainWindow,
        "_show_tab_menu",
        lambda self, index, global_pos: opened.append((index, global_pos.toTuple())),
    )
    position = bar.tabRect(1).center()
    global_position = bar.mapToGlobal(position)
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, position, global_position)

    handled = window.eventFilter(bar, event)

    try:
        assert handled is True
        assert window.tabs.currentIndex() == 1
        assert opened == [(1, global_position.toTuple())]
    finally:
        window.close()


def test_tab_bar_double_click_event_prompts_rename(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    window.new_session()
    bar = window.tabs.tabBar()
    prompted: list[int] = []
    monkeypatch.setattr(
        MainWindow,
        "_prompt_rename",
        lambda self, index: prompted.append(index),
    )

    def dbl_click(point: QPointF) -> QMouseEvent:
        return QMouseEvent(
            QEvent.Type.MouseButtonDblClick,
            point,
            point,
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

    inside = dbl_click(QPointF(bar.tabRect(1).center()))
    outside = dbl_click(QPointF(bar.width() - 2, bar.tabRect(1).center().y()))

    try:
        assert window.eventFilter(bar, inside) is True
        assert prompted == [1]
        assert window.eventFilter(bar, outside) is False
        assert prompted == [1]
    finally:
        window.close()


def test_ask_session_title_uses_dialog_editor(qtbot: object, monkeypatch: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    captured: dict[str, object] = {}

    def fake_exec(dialog: QInputDialog) -> int:
        editor = dialog.findChild(QLineEdit)
        captured["editor"] = editor is not None
        if editor is not None:
            captured["max_length"] = editor.maxLength()
            captured["initial"] = editor.text()
            editor.setText("水泵控制器")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QInputDialog, "exec", fake_exec)
    result = window._ask_session_title("会话 1")

    try:
        assert result == "水泵控制器"
        assert captured.get("editor") is True
        assert captured.get("max_length") == MAX_SESSION_TITLE_LENGTH
        assert captured.get("initial") == "会话 1"
    finally:
        window.close()


def test_sidebar_content_stays_top_aligned(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        window.resize(1180, 760)
        qtbot.waitUntil(lambda: tab.sidebar.verticalScrollBar().maximum() == 0, timeout=2000)

        layout = tab.sidebar_content.layout()
        assert layout.itemAt(layout.count() - 1).spacerItem() is not None
        viewport_height = tab.sidebar.viewport().height()
        assert tab.log_panel.geometry().bottom() < viewport_height - 20
    finally:
        window.close()


def test_sidebar_width_default_and_clamps(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        assert tab.sidebar.minimumWidth() == 260
        assert tab.sidebar.maximumWidth() == 360
        assert tab.layout_splitter.sizes()[0] == 272

        tab.apply_layout_state(visible=True, width=500, content_splitter_state=None)
        assert tab.layout_state()[1] == 360

        tab.apply_layout_state(visible=True, width=100, content_splitter_state=None)
        assert tab.layout_state()[1] == 260

        tab.layout_splitter.moveSplitter(10, 1)
        assert tab.layout_state()[1] == 260

        tab.layout_splitter.moveSplitter(900, 1)
        assert tab.layout_state()[1] == 360
    finally:
        window.close()
