"""测试主窗口的标签、头部、状态条与侧栏交互。"""

from collections import Counter

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QContextMenuEvent, QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QInputDialog,
    QLineEdit,
    QMenuBar,
    QMessageBox,
    QScrollArea,
    QToolBar,
)
from tests.fixtures.fakes import FakeTransport
from tests.fixtures.ui_helpers import (
    RecordingStore,
    build_window,
    build_window_with_store,
    connect_session,
    current_tab,
    disconnect_session,
)

from qserialtool.application import MAX_SESSION_TITLE_LENGTH
from qserialtool.ui import MainWindow, data_colors
from qserialtool.ui.empty_state import NEW_SESSION_HREF
from qserialtool.ui.style_sheet import tokens


def test_session_tab_places_settings_in_left_sidebar_and_toggles(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    assert tab.layout_splitter.widget(0) is tab.sidebar
    assert tab.layout_splitter.widget(1) is tab.main_content
    assert isinstance(tab.sidebar, QScrollArea)
    assert tab.sidebar.widget() is tab.sidebar_content
    assert tab.connection_panel.parentWidget() is tab.sidebar_content
    assert tab.receive_panel.settings_card.parentWidget() is tab.sidebar_content
    assert tab.log_panel.parentWidget() is tab.sidebar_content
    assert tab.receive_send_splitter.widget(0) is tab.receive_panel
    assert tab.receive_send_splitter.widget(1) is tab.send_panel
    assert tab.sidebar.isVisible()

    qtbot.mouseClick(window.sidebar_toggle_button, Qt.MouseButton.LeftButton)
    assert not tab.sidebar.isVisible()
    assert window.sidebar_toggle_button.text() == "展开设置"

    qtbot.mouseClick(window.sidebar_toggle_button, Qt.MouseButton.LeftButton)
    assert tab.sidebar.isVisible()
    assert window.sidebar_toggle_button.text() == "收起设置"
    assert tab.layout_state()[0] is True
    window.close()


def test_send_panel_and_content_fit_narrow_window(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    window.resize(900, 600)
    # 发送区在最小窗口下必须完整放下；阈值随字体度量变化（构建脚本用 offscreen
    # 泛型字体），按实际可用宽度相对判断，不依赖固定像素预算。
    assert tab.send_panel.minimumSizeHint().width() <= tab.send_panel.width()
    # 接收标题行已整行移除：操作按钮改挂侧栏卡片，不再参与接收区宽度竞争。
    assert tab.receive_panel.settings_card.isAncestorOf(tab.receive_panel.pause_button)
    assert tab.receive_panel.settings_card.isAncestorOf(tab.receive_panel.clear_button)
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
    assert window.menu_button.parentWidget() is corner
    # “+”由自定义标签栏承载，跟随最后一个标签而不是固定在角落。
    assert window.tabs.tabBar() is window.tab_bar
    assert window.new_tab_button.parentWidget() is window.tab_bar
    assert window.new_tab_button.isVisible()
    assert window.menu_button.isVisible()
    # 侧栏折叠与终端/分栏按钮移入标签行顶部角落，替换原接收标题行两端的位置。
    assert window.sidebar_toggle_button.parentWidget() is corner
    assert window.view_toggle_button.parentWidget() is corner
    assert window.sidebar_toggle_button.isVisible()
    assert window.view_toggle_button.isVisible()
    if window.window_buttons is not None:
        assert window.window_buttons.parentWidget() is corner
        assert window.window_buttons.isVisible()
    window.close()


def test_top_buttons_follow_active_tab_state(qtbot: object) -> None:
    """顶部侧栏/视图按钮反映当前标签状态，并在切换标签时同步。"""
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    first = current_tab(window)

    try:
        assert not window.sidebar_toggle_button.isChecked()
        assert window.view_toggle_button.text() == "终端"

        # 第一个标签收起侧栏并进入终端视图。
        qtbot.mouseClick(window.sidebar_toggle_button, Qt.MouseButton.LeftButton)
        qtbot.mouseClick(window.view_toggle_button, Qt.MouseButton.LeftButton)
        assert not first.sidebar.isVisible()
        assert first.view_mode == "terminal"
        assert window.sidebar_toggle_button.text() == "展开设置"
        assert window.view_toggle_button.text() == "分栏"
        assert window.view_toggle_button.isChecked()

        # 新标签继承当前标签的布局状态（侧栏保持收起、视图回到分栏），
        # 按钮随当前标签更新。
        second = window.new_session()
        assert window.tabs.currentWidget() is second
        assert window.sidebar_toggle_button.isChecked()
        assert window.sidebar_toggle_button.text() == "展开设置"
        assert not window.view_toggle_button.isChecked()
        assert window.view_toggle_button.text() == "终端"

        window.tabs.setCurrentIndex(0)
        assert window.sidebar_toggle_button.isChecked()
        assert window.sidebar_toggle_button.text() == "展开设置"
        assert window.view_toggle_button.isChecked()
        assert window.view_toggle_button.text() == "分栏"
        assert second.view_mode == "split"
    finally:
        window.close()


def test_top_buttons_disabled_without_sessions(qtbot: object) -> None:
    """没有会话标签时顶部按钮禁用，避免对空标签操作。"""
    transport = FakeTransport()
    window = build_window(qtbot, transport)

    try:
        window._close_tab(0)
        assert window.tabs.count() == 0
        assert not window.sidebar_toggle_button.isEnabled()
        assert not window.view_toggle_button.isEnabled()

        window.new_session()
        assert window.sidebar_toggle_button.isEnabled()
        assert window.view_toggle_button.isEnabled()
    finally:
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


def test_clear_receive_action_shortcut_and_confirmation(
    qtbot: object,
    monkeypatch: object,
) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    questions: list[object] = []

    def fake_question(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
        questions.append(args)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", fake_question)

    try:
        action = next(item for item in window.main_menu.actions() if item.text() == "清空接收区")
        assert action.shortcut().toString() == "Ctrl+L"
        assert action in window.actions()

        # 空缓冲不弹确认，直接走清空流程。
        action.trigger()
        assert questions == []
        assert tab.receive_panel.output.toPlainText() == ""

        connect_session(qtbot, tab)
        transport.push_read(b"payload")
        qtbot.waitUntil(lambda: "payload" in tab.receive_panel.output.toPlainText(), timeout=2000)

        action.trigger()
        assert questions
        qtbot.waitUntil(lambda: tab.controller.records == (), timeout=2000)
        assert tab.receive_panel.output.toPlainText() == ""
    finally:
        tab.controller.close(force=True)
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
        # 内容整体收在视口内（顶部对齐、底部空区由尾部弹簧承接）。
        assert tab.log_panel.geometry().bottom() < viewport_height
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


def test_empty_state_guides_until_new_session_added(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    label = window._empty_state

    try:
        assert not label.isVisible()

        window._close_tab(0)
        assert window.tabs.count() == 0
        assert label.isVisible()
        assert window.tab_bar.height() > 0
        assert window.tab_bar.new_tab_button.isVisible()
        assert window._header_tools.height() > 0
        assert label.y() == window.tab_bar.height()
        assert "Ctrl+T" in label.text()
        assert NEW_SESSION_HREF in label.text()
        assert not label.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert label.textInteractionFlags() & Qt.TextInteractionFlag.LinksAccessibleByMouse

        window.resize(1000, 700)
        qtbot.waitUntil(
            lambda: label.width() == window.tabs.width() and label.y() == window.tab_bar.height(),
            timeout=2000,
        )

        window.new_session()
        assert not label.isVisible()
    finally:
        window.close()


def test_empty_state_link_starts_session(qtbot: object) -> None:
    """空态文案里的“新建会话”链接直接新建会话，未知链接被忽略。"""
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    label = window._empty_state

    try:
        window._close_tab(0)
        assert window.tabs.count() == 0

        label.linkActivated.emit("other-link")
        assert window.tabs.count() == 0

        label.linkActivated.emit(NEW_SESSION_HREF)
        assert window.tabs.count() == 1
        assert not label.isVisible()
    finally:
        window.close()


def test_empty_state_link_follows_theme_switch(qtbot: object) -> None:
    """链接颜色随主题切换重新解析，按当前主题的强调色渲染。"""
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    label = window._empty_state

    def dominant_link_color() -> str:
        image = label.grab().toImage()
        counter: Counter = Counter()
        for y in range(image.height()):
            for x in range(image.width()):
                rgb = image.pixel(x, y)
                if ((rgb & 0xFF) - ((rgb >> 16) & 0xFF)) > 40:
                    color = f"#{(rgb >> 16) & 0xFF:02x}{(rgb >> 8) & 0xFF:02x}{rgb & 0xFF:02x}"
                    counter[color] += 1
        assert counter, "未在空态文案里找到蓝调链接像素"
        return counter.most_common(1)[0][0]

    try:
        window._close_tab(0)
        label.resize(360, 160)

        for theme in ("light", "dark"):
            action = next(a for a in window.theme_actions if a.data() == theme)
            action.setChecked(True)
            assert dominant_link_color() == tokens(theme).accent.lower()
    finally:
        window.close()
