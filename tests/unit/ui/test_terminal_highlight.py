"""测试终端视图的地址与链接模式识别。"""

import pytest

from qserialtool.ui.terminal_highlight import find_highlights


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
