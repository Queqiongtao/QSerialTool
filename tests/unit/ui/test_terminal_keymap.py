"""测试逐键终端模式的按键映射。"""

from PySide6.QtCore import Qt

from qserialtool.ui.terminal_keymap import raw_key_input

_NO_MODIFIER = Qt.KeyboardModifier.NoModifier
_SHIFT = Qt.KeyboardModifier.ShiftModifier
_CONTROL = Qt.KeyboardModifier.ControlModifier
_ALT = Qt.KeyboardModifier.AltModifier


def test_printable_text_is_returned_for_encoding() -> None:
    assert raw_key_input(Qt.Key.Key_A, "a", _NO_MODIFIER) == "a"
    assert raw_key_input(Qt.Key.Key_Space, " ", _NO_MODIFIER) == " "
    assert raw_key_input(Qt.Key.Key_A, "中", _NO_MODIFIER) == "中"


def test_tab_and_backtab_sequences() -> None:
    assert raw_key_input(Qt.Key.Key_Tab, "\t", _NO_MODIFIER) == b"\t"
    assert raw_key_input(Qt.Key.Key_Tab, "\t", _SHIFT) == b"\x1b[Z"
    assert raw_key_input(Qt.Key.Key_Backtab, "\x0b", _SHIFT) == b"\x1b[Z"


def test_enter_is_left_to_line_ending_handler() -> None:
    assert raw_key_input(Qt.Key.Key_Return, "\r", _NO_MODIFIER) is None
    assert raw_key_input(Qt.Key.Key_Enter, "\r", _NO_MODIFIER) is None


def test_editing_and_escape_keys() -> None:
    assert raw_key_input(Qt.Key.Key_Backspace, "\x08", _NO_MODIFIER) == b"\x7f"
    assert raw_key_input(Qt.Key.Key_Backspace, "\x08", _CONTROL) == b"\x08"
    assert raw_key_input(Qt.Key.Key_Escape, "\x1b", _NO_MODIFIER) == b"\x1b"


def test_arrow_keys_and_modifiers() -> None:
    assert raw_key_input(Qt.Key.Key_Up, "", _NO_MODIFIER) == b"\x1b[A"
    assert raw_key_input(Qt.Key.Key_Down, "", _NO_MODIFIER) == b"\x1b[B"
    assert raw_key_input(Qt.Key.Key_Right, "", _NO_MODIFIER) == b"\x1b[C"
    assert raw_key_input(Qt.Key.Key_Left, "", _NO_MODIFIER) == b"\x1b[D"
    assert raw_key_input(Qt.Key.Key_Left, "", _CONTROL) == b"\x1b[1;5D"
    assert raw_key_input(Qt.Key.Key_Up, "", _SHIFT) == b"\x1b[1;2A"


def test_home_end_and_navigation_keys() -> None:
    assert raw_key_input(Qt.Key.Key_Home, "", _NO_MODIFIER) == b"\x1b[H"
    assert raw_key_input(Qt.Key.Key_End, "", _NO_MODIFIER) == b"\x1b[F"
    assert raw_key_input(Qt.Key.Key_Home, "", _CONTROL) == b"\x1b[1;5H"
    assert raw_key_input(Qt.Key.Key_Delete, "", _NO_MODIFIER) == b"\x1b[3~"
    assert raw_key_input(Qt.Key.Key_Insert, "", _NO_MODIFIER) == b"\x1b[2~"
    assert raw_key_input(Qt.Key.Key_PageUp, "", _NO_MODIFIER) == b"\x1b[5~"
    assert raw_key_input(Qt.Key.Key_PageDown, "", _NO_MODIFIER) == b"\x1b[6~"
    assert raw_key_input(Qt.Key.Key_Delete, "", _CONTROL) == b"\x1b[3;5~"


def test_control_letters_map_to_control_codes() -> None:
    assert raw_key_input(Qt.Key.Key_A, "a", _CONTROL) == b"\x01"
    assert raw_key_input(Qt.Key.Key_C, "c", _CONTROL) == b"\x03"
    assert raw_key_input(Qt.Key.Key_D, "d", _CONTROL) == b"\x04"
    assert raw_key_input(Qt.Key.Key_R, "r", _CONTROL) == b"\x12"
    assert raw_key_input(Qt.Key.Key_W, "w", _CONTROL) == b"\x17"
    assert raw_key_input(Qt.Key.Key_Z, "z", _CONTROL) == b"\x1a"
    assert raw_key_input(Qt.Key.Key_W, "w", _CONTROL | _SHIFT) == b"\x17"


def test_control_punctuation_and_space() -> None:
    assert raw_key_input(Qt.Key.Key_Space, " ", _CONTROL) == b"\x00"
    assert raw_key_input(Qt.Key.Key_BracketLeft, "[", _CONTROL) == b"\x1b"
    assert raw_key_input(Qt.Key.Key_Backslash, "\\", _CONTROL) == b"\x1c"
    assert raw_key_input(Qt.Key.Key_BracketRight, "]", _CONTROL) == b"\x1d"
    assert raw_key_input(Qt.Key.Key_AsciiCircum, "^", _CONTROL) == b"\x1e"
    assert raw_key_input(Qt.Key.Key_Underscore, "_", _CONTROL) == b"\x1f"
    assert raw_key_input(Qt.Key.Key_Question, "?", _CONTROL) == b"\x7f"


def test_alt_and_altgr() -> None:
    assert raw_key_input(Qt.Key.Key_A, "a", _ALT) == "\x1ba"
    assert raw_key_input(Qt.Key.Key_A, "a", _CONTROL | _ALT) == "a"
    assert raw_key_input(Qt.Key.Key_At, "@", _CONTROL | _ALT) == "@"


def test_unknown_keys_are_consumed_without_sending() -> None:
    assert raw_key_input(Qt.Key.Key_F1, "", _NO_MODIFIER) is None
    assert raw_key_input(Qt.Key.Key_F12, "", _NO_MODIFIER) is None
