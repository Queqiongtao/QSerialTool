"""逐键终端模式的按键到终端字节映射。"""

from PySide6.QtCore import Qt

# 这些键交给调用方处理：回车要按用户配置的换行发送，不能固定成一个字节。
_ENTER_KEYS = frozenset({Qt.Key.Key_Return, Qt.Key.Key_Enter})

_ARROW_LETTERS = {
    Qt.Key.Key_Up: b"A",
    Qt.Key.Key_Down: b"B",
    Qt.Key.Key_Right: b"C",
    Qt.Key.Key_Left: b"D",
}

_HOME_END_LETTERS = {
    Qt.Key.Key_Home: b"H",
    Qt.Key.Key_End: b"F",
}

_TILDE_KEYS = {
    Qt.Key.Key_Insert: b"2",
    Qt.Key.Key_Delete: b"3",
    Qt.Key.Key_PageUp: b"5",
    Qt.Key.Key_PageDown: b"6",
}

_CONTROL_PUNCTUATION = {
    Qt.Key.Key_Space: 0x00,
    Qt.Key.Key_BracketLeft: 0x1B,
    Qt.Key.Key_Backslash: 0x1C,
    Qt.Key.Key_BracketRight: 0x1D,
    Qt.Key.Key_AsciiCircum: 0x1E,
    Qt.Key.Key_Underscore: 0x1F,
    Qt.Key.Key_Question: 0x7F,
}


def raw_key_input(
    key: int,
    text: str,
    modifiers: Qt.KeyboardModifier,
) -> str | bytes | None:
    """把逐键模式的按键转换成待发送文本或固定终端序列。

    返回 ``str`` 表示交给上层按会话编码发送，返回 ``bytes`` 表示直接写入
    串口，返回 ``None`` 表示该键被消费但不产生数据。回车不在本函数处理，
    由调用方沿用现有“换行”设置。
    """
    if key in _ENTER_KEYS:
        return None

    shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
    control = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
    alt = bool(modifiers & Qt.KeyboardModifier.AltModifier)

    basic = _basic_sequence(key, shift=shift, control=control, alt=alt)
    if basic is not None:
        return basic

    # AltGr 在 Qt 中通常表现为 Ctrl+Alt；此时应优先发送键盘布局产生的字符。
    if text and control and alt:
        return text

    if control:
        code = _control_code(key)
        if code is not None:
            return bytes([code])

    if alt and text:
        return "\x1b" + text
    return text or None


def _basic_sequence(
    key: int,
    *,
    shift: bool,
    control: bool,
    alt: bool,
) -> bytes | None:
    """处理不依赖文本编码的固定终端序列。"""
    if key in {Qt.Key.Key_Tab, Qt.Key.Key_Backtab}:
        return b"\x1b[Z" if shift else b"\t"
    if key == Qt.Key.Key_Backspace:
        return b"\x08" if control else b"\x7f"
    if key == Qt.Key.Key_Escape:
        return b"\x1b"
    return _special_sequence(key, shift=shift, control=control, alt=alt)


def _special_sequence(
    key: int,
    *,
    shift: bool,
    control: bool,
    alt: bool,
) -> bytes | None:
    """返回方向键、导航键的 xterm 序列；普通键返回 ``None``。"""
    modifier = _xterm_modifier(shift=shift, control=control, alt=alt)
    if key in _ARROW_LETTERS:
        return _csi_with_modifier(_ARROW_LETTERS[key], modifier)
    if key in _HOME_END_LETTERS:
        return _csi_with_modifier(_HOME_END_LETTERS[key], modifier)
    if key in _TILDE_KEYS:
        return _tilde_sequence(_TILDE_KEYS[key], modifier)
    return None


def _xterm_modifier(*, shift: bool, control: bool, alt: bool) -> int:
    """按 xterm 的 modifier 参数编码：1 表示无修饰键。"""
    value = 1
    if shift:
        value += 1
    if alt:
        value += 2
    if control:
        value += 4
    return value


def _csi_with_modifier(letter: bytes, modifier: int) -> bytes:
    if modifier == 1:
        return b"\x1b[" + letter
    return b"\x1b[1;" + str(modifier).encode("ascii") + letter


def _tilde_sequence(number: bytes, modifier: int) -> bytes:
    if modifier == 1:
        return b"\x1b[" + number + b"~"
    return b"\x1b[" + number + b";" + str(modifier).encode("ascii") + b"~"


def _control_code(key: int) -> int | None:
    if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        return key - Qt.Key.Key_A + 1
    return _CONTROL_PUNCTUATION.get(key)
