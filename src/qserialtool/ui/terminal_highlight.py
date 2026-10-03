"""识别接收文本中的地址与链接片段，供终端视图叠加高亮。"""

import re

# 匹配按优先级排列：先命中的片段占用区间，后续模式跳过重叠部分。
_URL_PATTERN = re.compile(r"(?i)\b(?:https?|ftp)://[^\s<>\x22']+")
_EMAIL_PATTERN = re.compile(r"(?i)\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_MAC_PATTERN = re.compile(r"(?i)\b[0-9a-f]{2}(?:[:-][0-9a-f]{2}){5}\b")
_IPV4_PATTERN = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
)

_ORDERED_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (_URL_PATTERN, "link"),
    (_EMAIL_PATTERN, "link"),
    (_MAC_PATTERN, "address"),
    (_IPV4_PATTERN, "address"),
)

# 所有模式都必须包含其中至少一个字符，用于快速跳过无关文本。
_TRIGGER_CHARS = frozenset(".:-@/")
_URL_TRAILING_CHARS = ".,;:!?)]}'\x22"


def find_highlights(text: str) -> tuple[tuple[int, int, str], ...]:
    """返回文本中地址/链接片段的 (start, end, kind)，按位置升序且互不重叠。"""
    if not text or _TRIGGER_CHARS.isdisjoint(text):
        return ()
    claimed: list[tuple[int, int, str]] = []
    for pattern, kind in _ORDERED_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span()
            if pattern is _URL_PATTERN:
                end = _trim_url_end(text, start, end)
                if end <= start:
                    continue
            if _overlaps(claimed, start, end):
                continue
            claimed.append((start, end, kind))
    claimed.sort()
    return tuple(claimed)


def _trim_url_end(text: str, start: int, end: int) -> int:
    """去掉 URL 末尾的句读与右括号，避免把行尾标点算进链接。"""
    while end > start and text[end - 1] in _URL_TRAILING_CHARS:
        end -= 1
    return end


def _overlaps(claimed: list[tuple[int, int, str]], start: int, end: int) -> bool:
    return any(start < other_end and other_start < end for other_start, other_end, _ in claimed)
