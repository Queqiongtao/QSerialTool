"""HEX、文本编码和换行策略。"""

from .errors import HexFormatError, TextEncodingError, ValidationError
from .types import (
    SUPPORTED_ENCODINGS,
    SUPPORTED_LINE_ENDINGS,
    EncodingName,
    LineEnding,
)

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_LINE_ENDING_BYTES: dict[LineEnding, bytes] = {
    "none": b"",
    "cr": b"\r",
    "lf": b"\n",
    "crlf": b"\r\n",
}


def _validate_encoding(encoding: str) -> EncodingName:
    if encoding not in SUPPORTED_ENCODINGS:
        supported = "、".join(sorted(SUPPORTED_ENCODINGS))
        raise ValidationError(f"不支持的文本编码：{encoding}。支持：{supported}。")
    return encoding  # type: ignore[return-value]


def parse_hex(text: str) -> bytes:
    """把连续或空白分隔的 HEX 文本解析为原始字节。"""
    if not isinstance(text, str):
        raise HexFormatError("HEX 输入必须是字符串。")
    compact = "".join(character for character in text if not character.isspace())
    if not compact:
        return b""
    if len(compact) % 2 != 0:
        raise HexFormatError("HEX 数据必须由完整的字节组成。")
    invalid = next((character for character in compact if character not in _HEX_DIGITS), None)
    if invalid is not None:
        raise HexFormatError(f"HEX 数据包含非法字符：{invalid!r}。")
    try:
        return bytes.fromhex(compact)
    except ValueError as exc:
        raise HexFormatError("HEX 数据无法解析。") from exc


def format_hex(data: bytes) -> str:
    """把字节格式化为大写、空格分隔的 HEX 文本。"""
    if not isinstance(data, bytes):
        raise HexFormatError("HEX 格式化输入必须是 bytes。")
    return data.hex(" ").upper()


def _format_invalid_bytes(data: bytes) -> str:
    return "".join(f"<{value:02X}>" for value in data)


class IncrementalTextDecoder:
    """在未知读取边界下保持字节序列状态。"""

    def __init__(self, encoding: EncodingName) -> None:
        self.encoding = _validate_encoding(encoding)
        self._pending = bytearray()

    def decode(self, data: bytes, *, final: bool = False) -> str:
        """解码一个数据块；未完成的多字节序列会保留到下一块。"""
        if not isinstance(data, bytes):
            raise TextEncodingError("文本解码输入必须是 bytes。")
        if type(final) is not bool:
            raise TextEncodingError("final 参数必须是布尔值。")
        self._pending.extend(data)
        return self._decode_pending(final=final)

    def _decode_pending(self, *, final: bool) -> str:
        parts: list[str] = []
        while self._pending:
            raw = bytes(self._pending)
            try:
                parts.append(raw.decode(self.encoding, errors="strict"))
            except UnicodeDecodeError as exc:
                if exc.start:
                    parts.append(raw[: exc.start].decode(self.encoding, errors="strict"))
                    del self._pending[: exc.start]
                    continue
                if not final and exc.end >= len(raw):
                    break
                invalid_end = exc.end if exc.end > exc.start else exc.start + 1
                parts.append(_format_invalid_bytes(raw[exc.start : invalid_end]))
                del self._pending[:invalid_end]
                continue
            self._pending.clear()
            break

        if final and self._pending:
            parts.append(_format_invalid_bytes(bytes(self._pending)))
            self._pending.clear()
        return "".join(parts)

    def reset(self) -> None:
        """清空所有尚未完成的解码状态。"""
        self._pending.clear()


def decode_text(data: bytes, encoding: EncodingName) -> str:
    """完整解码一段字节，并为非法字节生成 HEX 占位。"""
    decoder = IncrementalTextDecoder(encoding)
    return decoder.decode(data, final=True)


def encode_text(text: str, encoding: EncodingName) -> bytes:
    """按指定编码严格编码文本。"""
    if not isinstance(text, str):
        raise TextEncodingError("待编码内容必须是字符串。")
    normalized = _validate_encoding(encoding)
    try:
        return text.encode(normalized, errors="strict")
    except UnicodeEncodeError as exc:
        raise TextEncodingError(f"文本无法使用 {normalized} 编码。") from exc


def append_line_ending(data: bytes, line_ending: LineEnding) -> bytes:
    """按发送策略在原始字节后追加换行。"""
    if not isinstance(data, bytes):
        raise ValidationError("发送数据必须是 bytes。")
    if line_ending not in SUPPORTED_LINE_ENDINGS:
        raise ValidationError(f"不支持的换行策略：{line_ending}。")
    return data + _LINE_ENDING_BYTES[line_ending]
