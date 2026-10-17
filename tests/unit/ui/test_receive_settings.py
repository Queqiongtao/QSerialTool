"""测试侧边栏“接收设置”卡片的内容与按视图模式显隐。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QWidget
from tests.fixtures.fakes import FakeTransport
from tests.fixtures.ui_helpers import build_window, connect_session, current_tab

from qserialtool.ui import ReceivePanel


def test_receive_settings_card_lives_in_sidebar(qtbot: object) -> None:
    """卡片挂在侧栏“串口设置”与“日志与导出”之间，接收面板内不再有标题行。"""
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    panel = tab.receive_panel

    try:
        layout = tab.sidebar_content.layout()
        assert layout.itemAt(0).widget() is tab.connection_panel
        assert layout.itemAt(1).widget() is panel.settings_card
        assert layout.itemAt(2).widget() is tab.log_panel
        # 接收面板只剩输出区：标题行整行移除，接收内容直接顶到标签行下方。
        assert panel.layout().count() == 1
        assert panel.layout().itemAt(0).widget() is panel.output
    finally:
        window.close()


def test_receive_settings_rows_follow_view_mode(qtbot: object) -> None:
    """分栏显示格式/时间戳/RX/TX，终端显示高亮/终端时间戳与发送设置。"""
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    panel = tab.receive_panel

    try:
        assert panel._mode_row.isVisibleTo(tab)
        assert panel._filters_row.isVisibleTo(tab)
        assert not panel._terminal_row.isVisibleTo(tab)
        assert not panel._tools_row.isVisibleTo(tab)
        assert not tab.send_settings_button.isVisibleTo(tab)

        qtbot.mouseClick(window.view_toggle_button, Qt.MouseButton.LeftButton)

        assert not panel._mode_row.isVisibleTo(tab)
        assert not panel._filters_row.isVisibleTo(tab)
        assert panel._terminal_row.isVisibleTo(tab)
        assert panel._tools_row.isVisibleTo(tab)
        assert tab.send_settings_button.isVisibleTo(tab)

        qtbot.mouseClick(window.view_toggle_button, Qt.MouseButton.LeftButton)

        assert panel._mode_row.isVisibleTo(tab)
        assert panel._filters_row.isVisibleTo(tab)
        assert not panel._terminal_row.isVisibleTo(tab)
        assert not panel._tools_row.isVisibleTo(tab)
    finally:
        window.close()


def test_receive_settings_actions_toggle_pause_and_clear(
    qtbot: object,
    monkeypatch: object,
) -> None:
    """卡片里的暂停/清屏按钮保持原有行为。"""
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    panel = tab.receive_panel
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    )

    try:
        connect_session(qtbot, tab)
        transport.push_read(b"first")
        qtbot.waitUntil(lambda: "first" in panel.output.toPlainText(), timeout=2000)

        qtbot.mouseClick(panel.pause_button, Qt.MouseButton.LeftButton)
        assert panel.pause_button.text() == "继续"
        transport.push_read(b"second")
        qtbot.wait(120)
        assert "second" not in panel.output.toPlainText()

        qtbot.mouseClick(panel.pause_button, Qt.MouseButton.LeftButton)
        assert panel.pause_button.text() == "暂停"
        qtbot.waitUntil(lambda: "second" in panel.output.toPlainText(), timeout=2000)

        qtbot.mouseClick(panel.clear_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: panel.output.toPlainText() == "", timeout=2000)
    finally:
        tab.controller.close(force=True)
        window.close()


def test_receive_panel_construction_never_shows_parentless_widgets(
    qtbot: object,
    monkeypatch: object,
) -> None:
    """构造期不得对无父控件的控件执行 setVisible(True)，否则会闪出顶层小窗。"""
    shown_parentless: list[str] = []
    original = QWidget.setVisible

    def spy(self: QWidget, visible: bool) -> None:
        if visible and self.parent() is None:
            shown_parentless.append(type(self).__name__)
        original(self, visible)

    monkeypatch.setattr(QWidget, "setVisible", spy)
    panel = ReceivePanel(records_provider=lambda: (), clear_callback=lambda: 0)
    shown_during_construction = list(shown_parentless)
    qtbot.addWidget(panel)

    assert shown_during_construction == []
