"""测试 HEX、编码和换行领域能力。"""

from typing import cast

import pytest

from qserialtool.domain import (
    EncodingName,
    HexFormatError,
    IncrementalTextDecoder,
    LineEnding,
    TextEncodingError,
    ValidationError,
    append_line_ending,
    decode_text,
    encode_text,
    format_hex,
    parse_hex,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", b""),
        ("   ", b""),
        ("AA 01 ff", b"\xaa\x01\xff"),
        ("AA01", b"\xaa\x01"),
        ("AA\t01\nFF", b"\xaa\x01\xff"),
        ("AA\u300001", b"\xaa\x01"),
    ],
)
def test_parse_hex_accepts_compact_and_whitespace_separated_bytes(
    text: str,
    expected: bytes,
) -> None:
    assert parse_hex(text) == expected


@pytest.mark.parametrize("text", ["A", "GG", "AA:01", "ＡＡ", "中文", "AA 0Z"])
def test_parse_hex_rejects_invalid_input(text: str) -> None:
    with pytest.raises(HexFormatError):
        parse_hex(text)


def test_parse_hex_rejects_non_string_input() -> None:
    with pytest.raises(HexFormatError):
        parse_hex(cast(str, b"AA"))


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"", ""),
        (b"\xaa\x01\xff", "AA 01 FF"),
    ],
)
def test_format_hex_uses_uppercase_space_separated_output(data: bytes, expected: str) -> None:
    assert format_hex(data) == expected


def test_format_hex_rejects_non_bytes_input() -> None:
    with pytest.raises(HexFormatError):
        format_hex(cast(bytes, "AA"))


@pytest.mark.parametrize(
    ("encoding", "text", "expected"),
    [
        ("utf-8", "串口测试", "串口测试".encode()),
        ("gb18030", "中文设备", "中文设备".encode("gb18030")),
        ("ascii", "serial", b"serial"),
    ],
)
def test_encode_and_decode_text(encoding: EncodingName, text: str, expected: bytes) -> None:
    encoded = encode_text(text, encoding)
    assert encoded == expected
    assert decode_text(encoded, encoding) == text


def test_incremental_decoder_handles_utf8_split_across_chunks() -> None:
    data = "串口".encode()
    decoder = IncrementalTextDecoder("utf-8")

    assert decoder.decode(data[:1]) == ""
    assert decoder.decode(data[1:3]) == "串"
    assert decoder.decode(data[3:]) == "口"


def test_incremental_decoder_handles_gb18030_split_across_chunks() -> None:
    data = "中文".encode("gb18030")
    decoder = IncrementalTextDecoder("gb18030")

    assert decoder.decode(data[:1]) == ""
    assert decoder.decode(data[1:]) == "中文"


def test_incremental_decoder_marks_invalid_bytes() -> None:
    assert decode_text(b"\xff", "utf-8") == "<FF>"
    assert decode_text(b"\xc3(", "utf-8") == "<C3>("
    assert decode_text(b"\xe4\xb8", "utf-8") == "<E4><B8>"
    assert decode_text(b"\xff", "ascii") == "<FF>"


def test_incremental_decoder_reset_discards_partial_sequence() -> None:
    decoder = IncrementalTextDecoder("utf-8")
    assert decoder.decode(b"\xe4") == ""
    decoder.reset()
    assert decoder.decode("口".encode()) == "口"


def test_incremental_decoder_rejects_invalid_types() -> None:
    decoder = IncrementalTextDecoder("utf-8")
    with pytest.raises(TextEncodingError):
        decoder.decode(cast(bytes, "text"))
    with pytest.raises(TextEncodingError):
        decoder.decode(b"", final=cast(bool, 1))


def test_encode_text_rejects_ascii_with_chinese() -> None:
    with pytest.raises(TextEncodingError):
        encode_text("中文", "ascii")


def test_encode_text_rejects_non_string() -> None:
    with pytest.raises(TextEncodingError):
        encode_text(cast(str, b"text"), "utf-8")


@pytest.mark.parametrize(
    ("line_ending", "expected"),
    [
        ("none", b"data"),
        ("cr", b"data\r"),
        ("lf", b"data\n"),
        ("crlf", b"data\r\n"),
    ],
)
def test_append_line_ending(line_ending: LineEnding, expected: bytes) -> None:
    assert append_line_ending(b"data", line_ending) == expected


def test_append_line_ending_rejects_invalid_values() -> None:
    with pytest.raises(ValidationError):
        append_line_ending(cast(bytes, "data"), "none")
    with pytest.raises(ValidationError):
        append_line_ending(b"data", cast(LineEnding, "unsupported"))


def test_codec_rejects_unsupported_encoding() -> None:
    with pytest.raises(ValidationError):
        encode_text("text", cast(EncodingName, "utf-16"))
    with pytest.raises(ValidationError):
        IncrementalTextDecoder(cast(EncodingName, "utf-16"))
