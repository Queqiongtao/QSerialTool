"""测试终端视图高亮：模式识别与渲染叠加。"""

import pytest
from tests.fixtures.fakes import FakeTransport
from tests.fixtures.ui_helpers import (
    build_window,
    connect_session,
    current_tab,
    fragment_formats,
)

from qserialtool.ui.terminal_highlight import find_highlights
from qserialtool.ui.theme_manager import ansi_color, highlight_colors


def test_detects_ipv4_as_address() -> None:
    assert find_highlights("gw 192.168.1.1 up") == ((3, 14, "address"),)


@pytest.mark.parametrize("text", ["aa:bb:cc:dd:ee:ff", "AA-BB-CC-DD-EE-FF"])
def test_detects_mac_as_address(text: str) -> None:
    assert find_highlights(text) == ((0, 17, "address"),)


def test_detects_url_and_email_as_link() -> None:
    assert find_highlights("https://example.com/x") == ((0, 21, "link"),)
    assert find_highlights("mail me a@b.com now") == ((8, 15, "link"),)


def test_url_trailing_punctuation_is_trimmed() -> None:
    assert find_highlights("see http://a.com.") == ((4, 16, "link"),)


def test_url_containing_ip_is_a_single_link() -> None:
    assert find_highlights("http://10.0.0.1/") == ((0, 16, "link"),)


def test_rejects_out_of_range_ipv4() -> None:
    assert find_highlights("256.1.1.1") == ()


def test_multiple_matches_are_sorted() -> None:
    assert find_highlights("1.2.3.4 and 5.6.7.8") == (
        (0, 7, "address"),
        (12, 19, "address"),
    )


@pytest.mark.parametrize("text", ["", "plain text 12345", "hello world"])
def test_returns_empty_without_matches(text: str) -> None:
    assert find_highlights(text) == ()


@pytest.mark.parametrize(
    "text, expected",
    [
        ("OK", ((0, 2, "success"),)),
        ("ok", ((0, 2, "success"),)),
        ("Success", ((0, 7, "success"),)),
        ("PASS", ((0, 4, "success"),)),
        ("ERROR", ((0, 5, "error"),)),
        ("fail", ((0, 4, "error"),)),
        ("WARN", ((0, 4, "warning"),)),
    ],
)
def test_detects_keywords_case_insensitively(
    text: str, expected: tuple[tuple[int, int, str], ...]
) -> None:
    assert find_highlights(text) == expected


@pytest.mark.parametrize("text", ["OKAY", "SUCCESSFUL", "PASSED", "PASSWORD"])
def test_keywords_match_whole_words_only(text: str) -> None:
    assert find_highlights(text) == ()


def test_url_wins_over_embedded_keyword() -> None:
    assert find_highlights("http://a.com/OK") == ((0, 15, "link"),)


def test_address_and_keyword_can_coexist() -> None:
    assert find_highlights("1.2.3.4 OK") == ((0, 7, "address"), (8, 10, "success"))


def test_terminal_highlights_addresses_and_links_but_keeps_ansi_colors(
    qtbot: object,
) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"ip 10.0.0.1 link https://a.com/x\r\n")
        transport.push_read(b"\x1b[31m10.0.0.1\x1b[0m\r\n")

        qtbot.waitUntil(lambda: output.toPlainText().count("10.0.0.1") == 2, timeout=2000)
        formats = fragment_formats(output)
        colors = highlight_colors()

        assert ("10.0.0.1", colors.address) in formats
        assert ("https://a.com/x", colors.link) in formats
        assert ("10.0.0.1", ansi_color(1)) in formats
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_highlights_success_error_and_warning_keywords(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        output = tab.receive_panel.output

        transport.push_read(b"OK ERROR WARN\r\n")

        qtbot.waitUntil(lambda: output.toPlainText().strip() == "OK ERROR WARN", timeout=2000)
        formats = fragment_formats(output)
        colors = highlight_colors()

        assert ("OK", colors.success) in formats
        assert ("ERROR", colors.error) in formats
        assert ("WARN", colors.warning) in formats
    finally:
        tab.controller.close(force=True)
        window.close()


def test_terminal_highlight_toggle_disables_all_highlighting(qtbot: object) -> None:
    transport = FakeTransport()
    window = build_window(qtbot, transport)
    tab = current_tab(window)

    try:
        connect_session(qtbot, tab)
        tab.set_view_mode("terminal", persist=False)
        panel = tab.receive_panel
        output = panel.output
        colors = highlight_colors()

        transport.push_read(b"OK 10.0.0.1\r\n")
        qtbot.waitUntil(lambda: output.toPlainText().strip() == "OK 10.0.0.1", timeout=2000)
        assert ("OK", colors.success) in fragment_formats(output)
        assert ("10.0.0.1", colors.address) in fragment_formats(output)
        assert tab.to_preferences().highlight_enabled is True

        panel.highlight_check.setChecked(False)
        qtbot.waitUntil(
            lambda: (
                not any(
                    color in {colors.success, colors.address}
                    for _, color in fragment_formats(output)
                )
            ),
            timeout=2000,
        )
        assert tab.to_preferences().highlight_enabled is False

        panel.highlight_check.setChecked(True)
        qtbot.waitUntil(
            lambda: ("OK", colors.success) in fragment_formats(output),
            timeout=2000,
        )
    finally:
        tab.controller.close(force=True)
        window.close()
