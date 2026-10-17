"""测试接收标题行的溢出折叠与“⋯”菜单同步。"""

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QWidget
from tests.fixtures.fakes import FakeTransport
from tests.fixtures.ui_helpers import build_window, current_tab

from qserialtool.ui import ReceivePanel
from qserialtool.ui.receive_header import HeaderOverflow


def _expanded_controls(receive_panel: object) -> tuple:
    """标题行全展开时应可见的控件。"""
    return (
        receive_panel.mode_combo,
        receive_panel.timestamp_check,
        receive_panel.rx_check,
        receive_panel.tx_check,
        receive_panel.pause_button,
        receive_panel.clear_button,
        receive_panel.wrap_check,
        receive_panel.autoscroll_check,
    )


def _expand_to_fit(qtbot: object, window: object, tab: object) -> None:
    """按当前字体度量把窗口放大到接收标题行全部展开所需的宽度。"""
    receive_panel = tab.receive_panel
    overflow = receive_panel._header_overflow
    frame = window.width() - receive_panel.width()
    needed = overflow._required_width(set()) + frame + 16
    window.resize(needed, 760)
    qtbot.waitUntil(lambda: not overflow.folded_widgets(), timeout=2000)
    # 展开会改变可见性并触发再一次布局；等控件全部可见且落回面板内后再断言。
    qtbot.waitUntil(
        lambda: all(
            widget.isVisibleTo(tab) and widget.geometry().right() <= receive_panel.width()
            for widget in (*_expanded_controls(receive_panel), tab.view_toggle_button)
        ),
        timeout=2000,
    )


def test_receive_header_shows_all_controls_when_width_allows(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    receive_panel = tab.receive_panel
    overflow = receive_panel._header_overflow

    try:
        # 字体度量随平台变化（构建脚本用 offscreen 泛型字体）：按运行时所需宽度
        # 放大窗口而不是硬编码 1180，只要宽度足够，所有控件都必须展开。
        _expand_to_fit(qtbot, window, tab)

        assert not overflow.button.isVisibleTo(receive_panel)
        for widget in (*_expanded_controls(receive_panel), tab.view_toggle_button):
            assert widget.isVisibleTo(tab)
            assert widget.width() >= widget.sizeHint().width()
    finally:
        window.close()


def test_receive_header_folds_secondary_controls_when_narrow(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    receive_panel = tab.receive_panel
    overflow = receive_panel._header_overflow

    try:
        window.resize(900, 600)
        qtbot.waitUntil(lambda: bool(overflow.folded_widgets()), timeout=2000)
        # 折叠会改变可见性并触发再一次布局；等行尾“⋯”按钮落回面板内后读取稳定状态。
        qtbot.waitUntil(
            lambda: overflow.button.geometry().right() <= receive_panel.width(), timeout=2000
        )

        folded = overflow.folded_widgets()
        assert receive_panel.autoscroll_check in folded
        assert receive_panel.wrap_check in folded
        assert receive_panel.mode_combo not in folded
        assert tab.view_toggle_button not in folded

        # 暂停/清屏按折叠优先级最后兜底：能以折叠数据过滤与滚动开关换来的宽度放下时
        # 绝不折叠；字体度量更宽的环境（offscreen 构建）放不下时，也必须晚于时间戳
        # 与 RX/TX 过滤折叠。
        keep = {
            receive_panel.autoscroll_check,
            receive_panel.wrap_check,
            receive_panel.timestamp_check,
            receive_panel.rx_check,
            receive_panel.tx_check,
        }
        frame = window.width() - receive_panel.width()
        if overflow._required_width(keep) + frame <= window.width():
            assert receive_panel.pause_button not in folded
            assert receive_panel.clear_button not in folded
        elif receive_panel.pause_button in folded or receive_panel.clear_button in folded:
            assert receive_panel.timestamp_check in folded
            assert receive_panel.rx_check in folded
            assert receive_panel.tx_check in folded

        assert overflow.button.isVisibleTo(receive_panel)
        for widget in (
            receive_panel.mode_combo,
            receive_panel.pause_button,
            receive_panel.clear_button,
            tab.view_toggle_button,
            overflow.button,
        ):
            if widget in folded:
                continue
            assert widget.isVisibleTo(tab)
            assert widget.geometry().right() <= receive_panel.width()

        visible_actions = [
            action.text() for action in overflow.menu.actions() if action.isVisible()
        ]
        assert sorted(visible_actions) == sorted(widget.text() for widget in folded)
    finally:
        window.close()


def test_receive_header_overflow_action_mirrors_checkbox_state(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    receive_panel = tab.receive_panel
    overflow = receive_panel._header_overflow

    try:
        window.resize(900, 600)
        qtbot.waitUntil(
            lambda: receive_panel.autoscroll_check in overflow.folded_widgets(), timeout=2000
        )
        action = next(item for item in overflow.menu.actions() if item.text() == "自动滚动")
        assert action.isVisible()

        action.setChecked(False)
        assert not receive_panel.autoscroll_check.isChecked()
        receive_panel.autoscroll_check.setChecked(True)
        assert action.isChecked()

        _expand_to_fit(qtbot, window, tab)
        assert receive_panel.autoscroll_check.isChecked()

        window.resize(900, 600)
        qtbot.waitUntil(
            lambda: receive_panel.autoscroll_check in overflow.folded_widgets(), timeout=2000
        )
        texts = [item.text() for item in overflow.menu.actions() if item.isVisible()]
        assert len(texts) == len(set(texts))
    finally:
        window.close()


def test_header_overflow_skips_parentless_widgets(qtbot: object) -> None:
    """未挂父级的控件不得被显示成顶层窗口（启动期小窗闪烁的根因）。"""
    container = QWidget()
    qtbot.addWidget(container)
    row = QHBoxLayout(container)
    overflow = HeaderOverflow(container, row)
    checkbox = QCheckBox("测试项")
    overflow.register(checkbox, rank=20)

    overflow.reflow()
    # 无父控件：跳过可见性写入，保持显式隐藏，避免 setVisible(True) 变出顶层窗口。
    assert checkbox.isHidden()

    row.addWidget(checkbox)
    overflow.reflow()
    assert not checkbox.isHidden()


def test_receive_panel_construction_never_shows_parentless_widgets(
    qtbot: object,
    monkeypatch: object,
) -> None:
    """构造 ReceivePanel 期间不允许对无父控件的控件执行 setVisible(True)。"""
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
