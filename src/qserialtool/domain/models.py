"""领域模型和不可变数据快照。"""

from dataclasses import dataclass
from datetime import datetime

from .codecs import decode_text, format_hex
from .errors import UserFacingError, ValidationError
from .states import SessionState
from .types import (
    DEFAULT_LINE_ENDING,
    MAX_PERIODIC_INTERVAL_MS,
    MAX_SEND_HISTORY,
    MAX_SIDEBAR_WIDTH,
    MIN_PERIODIC_INTERVAL_MS,
    MIN_SIDEBAR_WIDTH,
    SUPPORTED_BYTESIZES,
    SUPPORTED_ENCODINGS,
    SUPPORTED_FLOW_CONTROLS,
    SUPPORTED_LOG_DIRECTIONS,
    SUPPORTED_LOG_FORMATS,
    SUPPORTED_PARITIES,
    SUPPORTED_STOPBITS,
    SUPPORTED_THEMES,
    SUPPORTED_VIEW_MODES,
    DisplayMode,
    EncodingName,
    FlowControl,
    LineEnding,
    LogDirection,
    LogFormat,
    Parity,
    Theme,
    ViewMode,
)


def _require_string(value: object, field_name: str, *, allow_empty: bool = False) -> None:
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} 必须是字符串。")
    if not allow_empty and not value.strip():
        raise ValidationError(f"{field_name} 不能为空。")


def _require_bool(value: object, field_name: str) -> None:
    if type(value) is not bool:
        raise ValidationError(f"{field_name} 必须是布尔值。")


def _require_non_negative_int(value: object, field_name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValidationError(f"{field_name} 必须是非负整数。")


@dataclass(frozen=True, slots=True)
class SerialConfig:
    """单个串口会话的连接参数。"""

    port: str
    baudrate: int = 115200
    bytesize: int = 8
    parity: Parity = "N"
    stopbits: float = 1.0
    flow_control: FlowControl = "none"
    dtr: bool = True
    rts: bool = True
    encoding: EncodingName = "utf-8"

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """验证不依赖当前连接状态的字段。"""
        _require_string(self.port, "端口", allow_empty=True)
        if type(self.baudrate) is not int or self.baudrate <= 0:
            raise ValidationError("波特率必须是正整数。")
        if type(self.bytesize) is not int or self.bytesize not in SUPPORTED_BYTESIZES:
            raise ValidationError("数据位仅允许 5、6、7、8。")
        if self.parity not in SUPPORTED_PARITIES:
            raise ValidationError("校验位仅允许 N、E、O、M、S。")
        if (
            type(self.stopbits) not in {int, float}
            or float(self.stopbits) not in SUPPORTED_STOPBITS
        ):
            raise ValidationError("停止位仅允许 1、1.5、2。")
        if self.flow_control not in SUPPORTED_FLOW_CONTROLS:
            raise ValidationError("流控策略不受支持。")
        _require_bool(self.dtr, "DTR")
        _require_bool(self.rts, "RTS")
        if self.encoding not in SUPPORTED_ENCODINGS:
            raise ValidationError("不支持的文本编码。")

    def validate_for_connect(self) -> None:
        """连接前验证，包括端口不能为空。"""
        self.validate()
        if not self.port.strip():
            raise ValidationError("连接前必须选择串口。")


@dataclass(frozen=True, slots=True)
class LogRecord:
    """一条不可变的串口数据或系统事件记录。"""

    timestamp_utc: datetime
    direction: LogDirection
    raw: bytes
    encoding: EncodingName
    text: str
    hex_text: str
    session_id: str

    def __post_init__(self) -> None:
        if self.timestamp_utc.tzinfo is None or self.timestamp_utc.utcoffset() is None:
            raise ValidationError("日志时间必须包含时区信息。")
        if self.direction not in SUPPORTED_LOG_DIRECTIONS:
            raise ValidationError("日志方向不受支持。")
        if not isinstance(self.raw, bytes):
            raise ValidationError("日志原始数据必须是 bytes。")
        if self.encoding not in SUPPORTED_ENCODINGS:
            raise ValidationError("日志编码不受支持。")
        _require_string(self.session_id, "会话 ID")
        if self.hex_text != format_hex(self.raw):
            raise ValidationError("HEX 文本必须由原始字节派生。")
        if self.text != decode_text(self.raw, self.encoding):
            raise ValidationError("文本必须由原始字节和编码派生。")

    @classmethod
    def from_bytes(
        cls,
        *,
        timestamp_utc: datetime,
        direction: LogDirection,
        raw: bytes,
        encoding: EncodingName,
        session_id: str,
    ) -> "LogRecord":
        """从原始字节创建记录，并生成派生的文本与 HEX。"""
        return cls(
            timestamp_utc=timestamp_utc,
            direction=direction,
            raw=raw,
            encoding=encoding,
            text=decode_text(raw, encoding),
            hex_text=format_hex(raw),
            session_id=session_id,
        )


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    """供 UI 只读渲染的会话状态快照。"""

    session_id: str
    title: str
    state: SessionState
    config: SerialConfig
    last_error: UserFacingError | None
    rx_bytes: int
    tx_bytes: int
    dropped_records: int

    def __post_init__(self) -> None:
        _require_string(self.session_id, "会话 ID")
        _require_string(self.title, "会话标题")
        if not isinstance(self.state, SessionState):
            raise ValidationError("会话状态必须是 SessionState。")
        if not isinstance(self.config, SerialConfig):
            raise ValidationError("config 必须是 SerialConfig。")
        if self.last_error is not None and not isinstance(self.last_error, UserFacingError):
            raise ValidationError("last_error 必须是 UserFacingError 或 None。")
        _require_non_negative_int(self.rx_bytes, "RX 字节数")
        _require_non_negative_int(self.tx_bytes, "TX 字节数")
        _require_non_negative_int(self.dropped_records, "丢弃记录数")


@dataclass(frozen=True, slots=True)
class SessionPreferences:
    """需要跨启动保存的单标签偏好。"""

    title: str
    config: SerialConfig
    display_mode: DisplayMode
    show_timestamp: bool
    show_rx: bool
    show_tx: bool
    autoscroll: bool
    auto_log_enabled: bool = False
    auto_log_format: LogFormat = "csv"
    auto_log_directory: str = ""
    send_history: tuple[str, ...] = ()
    send_mode: DisplayMode = "text"
    line_ending: LineEnding = DEFAULT_LINE_ENDING
    periodic_interval_ms: int = 1000
    view_mode: ViewMode = "split"

    def __post_init__(self) -> None:
        _require_string(self.title, "标签标题")
        if not isinstance(self.config, SerialConfig):
            raise ValidationError("config 必须是 SerialConfig。")
        if self.display_mode not in {"text", "hex"}:
            raise ValidationError("显示模式必须是 text 或 hex。")
        for value, field_name in (
            (self.show_timestamp, "show_timestamp"),
            (self.show_rx, "show_rx"),
            (self.show_tx, "show_tx"),
            (self.autoscroll, "autoscroll"),
            (self.auto_log_enabled, "auto_log_enabled"),
        ):
            _require_bool(value, field_name)
        if self.auto_log_format not in SUPPORTED_LOG_FORMATS:
            raise ValidationError("自动日志格式必须是 csv 或 txt。")
        _require_string(self.auto_log_directory, "自动日志目录", allow_empty=True)
        if not isinstance(self.send_history, tuple):
            raise ValidationError("发送历史必须是不可变 tuple。")
        if len(self.send_history) > MAX_SEND_HISTORY:
            raise ValidationError("发送历史不能超过 100 条。")
        if any(not isinstance(item, str) for item in self.send_history):
            raise ValidationError("发送历史只能包含字符串。")
        if self.send_mode not in {"text", "hex"}:
            raise ValidationError("发送模式必须是 text 或 hex。")
        if self.line_ending not in {"none", "cr", "lf", "crlf"}:
            raise ValidationError("换行策略不受支持。")
        if (
            type(self.periodic_interval_ms) is not int
            or not MIN_PERIODIC_INTERVAL_MS <= self.periodic_interval_ms <= MAX_PERIODIC_INTERVAL_MS
        ):
            raise ValidationError("周期发送间隔超出允许范围。")
        if self.view_mode not in SUPPORTED_VIEW_MODES:
            raise ValidationError("视图模式必须是 split 或 terminal。")


@dataclass(frozen=True, slots=True)
class AppConfig:
    """应用级配置模型。"""

    schema_version: int
    theme: Theme
    window_geometry: str | None
    window_state: str | None
    active_session_index: int
    sessions: tuple[SessionPreferences, ...]
    sidebar_visible: bool = True
    sidebar_width: int = 320
    content_splitter_state: str | None = None

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version <= 0:
            raise ValidationError("配置 schema 版本必须是正整数。")
        if self.theme not in SUPPORTED_THEMES:
            raise ValidationError("主题必须是 system、light 或 dark。")
        if self.window_geometry is not None and not isinstance(self.window_geometry, str):
            raise ValidationError("window_geometry 必须是字符串或 None。")
        if self.window_state is not None and not isinstance(self.window_state, str):
            raise ValidationError("window_state 必须是字符串或 None。")
        _require_non_negative_int(self.active_session_index, "活动标签索引")
        if not isinstance(self.sessions, tuple):
            raise ValidationError("sessions 必须是不可变 tuple。")
        if any(not isinstance(session, SessionPreferences) for session in self.sessions):
            raise ValidationError("sessions 只能包含 SessionPreferences。")
        if self.sessions and self.active_session_index >= len(self.sessions):
            raise ValidationError("活动标签索引超出范围。")
        if not self.sessions and self.active_session_index != 0:
            raise ValidationError("没有标签时活动标签索引必须为 0。")
        _require_bool(self.sidebar_visible, "sidebar_visible")
        if (
            type(self.sidebar_width) is not int
            or not MIN_SIDEBAR_WIDTH <= self.sidebar_width <= MAX_SIDEBAR_WIDTH
        ):
            raise ValidationError("侧栏宽度必须在 260 到 480 像素之间。")
        if self.content_splitter_state is not None and not isinstance(
            self.content_splitter_state, str
        ):
            raise ValidationError("content_splitter_state 必须是字符串或 None。")
