"""测试接收标题行的溢出折叠与“⋯”菜单同步。"""

from tests.fixtures.fakes import FakeTransport
from tests.fixtures.ui_helpers import build_window, current_tab


def test_receive_header_shows_all_controls_when_width_allows(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)
    receive_panel = tab.receive_panel
    overflow = receive_panel._header_overflow

    try:
        window.resize(1180, 760)
        qtbot.waitUntil(lambda: not overflow.folded_widgets(), timeout=2000)

        assert not overflow.button.isVisibleTo(receive_panel)
        for widget in (
            receive_panel.mode_combo,
            receive_panel.timestamp_check,
            receive_panel.rx_check,
            receive_panel.tx_check,
            receive_panel.pause_button,
            receive_panel.clear_button,
            receive_panel.wrap_check,
            receive_panel.autoscroll_check,
            tab.view_toggle_button,
        ):
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

        folded = overflow.folded_widgets()
        assert receive_panel.autoscroll_check in folded
        assert receive_panel.wrap_check in folded
        assert receive_panel.pause_button not in folded
        assert receive_panel.clear_button not in folded
        assert receive_panel.mode_combo not in folded
        assert tab.view_toggle_button not in folded

        assert overflow.button.isVisibleTo(receive_panel)
        for widget in (
            receive_panel.mode_combo,
            receive_panel.pause_button,
            receive_panel.clear_button,
            tab.view_toggle_button,
            overflow.button,
        ):
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

        window.resize(1180, 760)
        qtbot.waitUntil(lambda: not overflow.folded_widgets(), timeout=2000)
        assert receive_panel.autoscroll_check.isChecked()

        window.resize(900, 600)
        qtbot.waitUntil(
            lambda: receive_panel.autoscroll_check in overflow.folded_widgets(), timeout=2000
        )
        texts = [item.text() for item in overflow.menu.actions() if item.isVisible()]
        assert len(texts) == len(set(texts))
    finally:
        window.close()
