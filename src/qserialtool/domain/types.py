"""领域层共享类型别名和受支持取值。"""

from typing import Literal, TypeAlias

DisplayMode: TypeAlias = Literal["text", "hex"]
EncodingName: TypeAlias = Literal["utf-8", "gb18030", "ascii"]
FlowControl: TypeAlias = Literal["none", "xonxoff", "rtscts", "dsrdtr"]
LineEnding: TypeAlias = Literal["none", "cr", "lf", "crlf"]
LogDirection: TypeAlias = Literal["rx", "tx", "system"]
LogFormat: TypeAlias = Literal["csv", "txt"]
Parity: TypeAlias = Literal["N", "E", "O", "M", "S"]
Theme: TypeAlias = Literal["system", "light", "dark"]
ViewMode: TypeAlias = Literal["split", "terminal"]

MAX_SEND_HISTORY = 100
MIN_SIDEBAR_WIDTH = 260
MAX_SIDEBAR_WIDTH = 480
MIN_PERIODIC_INTERVAL_MS = 10
MAX_PERIODIC_INTERVAL_MS = 86_400_000
DEFAULT_LINE_ENDING: LineEnding = "lf"
MIN_DATA_FONT_SIZE = 8
MAX_DATA_FONT_SIZE = 28
DEFAULT_DATA_FONT_SIZE = 0

SUPPORTED_BYTESIZES = frozenset({5, 6, 7, 8})
SUPPORTED_ENCODINGS = frozenset({"utf-8", "gb18030", "ascii"})
SUPPORTED_FLOW_CONTROLS = frozenset({"none", "xonxoff", "rtscts", "dsrdtr"})
SUPPORTED_LINE_ENDINGS = frozenset({"none", "cr", "lf", "crlf"})
SUPPORTED_LOG_DIRECTIONS = frozenset({"rx", "tx", "system"})
SUPPORTED_LOG_FORMATS = frozenset({"csv", "txt"})
SUPPORTED_PARITIES = frozenset({"N", "E", "O", "M", "S"})
SUPPORTED_STOPBITS = frozenset({1.0, 1.5, 2.0})
SUPPORTED_THEMES = frozenset({"system", "light", "dark"})
SUPPORTED_VIEW_MODES = frozenset({"split", "terminal"})
