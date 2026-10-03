"""测试行式滚动缓冲终端模型。"""

import pytest

from qserialtool.domain import TerminalScreen, TerminalStyle, ValidationError


def test_plain_text_creates_lines() -> None:
    screen = TerminalScreen()
    screen.feed("hello\nworld")

    assert screen.text_lines() == ("hello", "world")
    assert screen.cursor == (1, 5)


def test_carriage_return_overwrites_line_start() -> None:
    screen = TerminalScreen()
    screen.feed("progress 10%\rprogress 90%")

    assert screen.text_lines() == ("progress 90%",)


def test_backspace_moves_cursor_without_erasing() -> None:
    screen = TerminalScreen()
    screen.feed("abcd\b\bZ")

    assert screen.text_lines() == ("abZd",)
    assert screen.cursor == (0, 3)


def test_crlf_uses_single_line_break() -> None:
    screen = TerminalScreen()
    screen.feed("a\r\nb")

    assert screen.text_lines() == ("a", "b")


def test_tab_advances_to_next_stop() -> None:
    screen = TerminalScreen()
    screen.feed("a\tb")

    assert screen.text_lines() == ("a       b",)
    assert screen.cursor == (0, 9)


def test_sgr_sets_and_resets_style() -> None:
    screen = TerminalScreen()
    screen.feed("\x1b[31mA\x1b[0mB")
    row = screen.lines()[0]

    assert row[0].char == "A"
    assert row[0].style == TerminalStyle(fg=1)
    assert row[1].char == "B"
    assert row[1].style == TerminalStyle()


def test_sgr_supports_bold_bright_and_background() -> None:
    screen = TerminalScreen()
    screen.feed("\x1b[1;94;47mX")

    assert screen.lines()[0][0].style == TerminalStyle(fg=12, bg=7, bold=True)


def test_sgr_ignores_unsupported_parameters() -> None:
    screen = TerminalScreen()
    screen.feed("\x1b[3mA\x1b[53mB")

    assert screen.lines()[0][0].style == TerminalStyle()
    assert screen.lines()[0][1].style == TerminalStyle()


def test_sgr_supports_256_color_palette() -> None:
    screen = TerminalScreen()
    screen.feed("\x1b[38;5;196mA\x1b[48;5;21mB")
    row = screen.lines()[0]

    assert row[0].style == TerminalStyle(fg=196)
    assert row[1].style == TerminalStyle(fg=196, bg=21)


def test_sgr_keeps_bold_around_extended_color() -> None:
    screen = TerminalScreen()
    screen.feed("\x1b[1;38;5;0mA\x1b[0mB")
    row = screen.lines()[0]

    assert row[0].style == TerminalStyle(fg=0, bold=True)
    assert row[1].style == TerminalStyle()


def test_sgr_ignores_truecolor_but_keeps_other_attributes() -> None:
    screen = TerminalScreen()
    screen.feed("\x1b[1;38;2;255;0;0mA")

    assert screen.lines()[0][0].style == TerminalStyle(bold=True)


def test_sgr_extended_color_with_missing_parameters_is_ignored() -> None:
    screen = TerminalScreen()
    screen.feed("\x1b[1;38;5mA")
    screen.feed("B")
    row = screen.lines()[0]

    assert row[0].style == TerminalStyle(bold=True)
    assert row[1].style == TerminalStyle(bold=True)


def test_sgr_ignores_out_of_range_palette_index() -> None:
    screen = TerminalScreen()
    screen.feed("\x1b[38;5;256mA")

    assert screen.lines()[0][0].style == TerminalStyle()


def test_cursor_movement_and_position() -> None:
    screen = TerminalScreen()
    screen.feed("abc\x1b[2DZ")

    assert screen.text_lines() == ("aZc",)
    assert screen.cursor == (0, 2)

    screen.feed("\x1b[3;3HX")

    assert screen.cursor == (2, 3)
    assert screen.text_lines()[2] == "  X"


def test_cursor_movement_clamps_at_edges() -> None:
    screen = TerminalScreen()
    screen.feed("\x1b[5A\x1b[5D")

    assert screen.cursor == (0, 0)

    screen.feed("\x1b[9C")

    assert screen.cursor == (0, 9)


def test_erase_line_from_cursor() -> None:
    screen = TerminalScreen()
    screen.feed("abcdef\x1b[1;4H\x1b[K")

    assert tuple(line.rstrip() for line in screen.text_lines()) == ("abc",)


def test_erase_display_from_cursor_removes_following_rows() -> None:
    screen = TerminalScreen()
    screen.feed("one\ntwo\nthree")
    screen.feed("\x1b[2;2H\x1b[J")

    assert tuple(line.rstrip() for line in screen.text_lines()) == ("one", "t")


def test_erase_display_all_resets_cursor() -> None:
    screen = TerminalScreen()
    screen.feed("abc\x1b[2J")

    assert screen.text_lines() == ("",)
    assert screen.cursor == (0, 0)


def test_private_and_unknown_sequences_are_ignored() -> None:
    screen = TerminalScreen()
    screen.feed("\x1b[?25lA\x1b[999zB")

    assert screen.text_lines() == ("AB",)


def test_incomplete_sequences_wait_for_more_data() -> None:
    screen = TerminalScreen()
    screen.feed("A\x1b[3")

    assert screen.text_lines() == ("A",)

    screen.feed("1mB")
    row = screen.lines()[0]

    assert row[0].char == "A"
    assert row[1].char == "B"
    assert row[1].style == TerminalStyle(fg=1)


def test_wide_characters_occupy_two_cells() -> None:
    screen = TerminalScreen()
    screen.feed("中a")
    row = screen.lines()[0]

    assert row[0].char == "中"
    assert row[1].trailing is True
    assert row[2].char == "a"
    assert screen.text_lines() == ("中a",)
    assert screen.cursor == (0, 3)


def test_combining_character_attaches_to_previous_cell() -> None:
    screen = TerminalScreen()
    screen.feed("e\u0301x")
    row = screen.lines()[0]

    assert row[0].char == "e\u0301"
    assert row[1].char == "x"


def test_long_line_wraps_at_column_limit() -> None:
    screen = TerminalScreen(max_columns=4)
    screen.feed("abcde")

    assert screen.text_lines() == ("abcd", "e")
    assert screen.cursor == (1, 1)


def test_scrollback_is_trimmed_to_max_rows() -> None:
    screen = TerminalScreen(max_rows=3)
    for index in range(6):
        screen.feed(f"line{index}\n")

    lines = screen.text_lines()

    assert len(lines) == 3
    assert lines == ("line4", "line5", "")


def test_reset_clears_text_and_style() -> None:
    screen = TerminalScreen()
    screen.feed("abc\x1b[31m\n")

    screen.reset()

    assert screen.text_lines() == ("",)
    assert screen.cursor == (0, 0)

    screen.feed("x")

    assert screen.lines()[0][0].style == TerminalStyle()


@pytest.mark.parametrize("kwargs", [{"max_rows": 0}, {"max_columns": 0}])
def test_rejects_non_positive_limits(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        TerminalScreen(**kwargs)
