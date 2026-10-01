"""领域错误和可供界面展示的错误结构。"""

from dataclasses import dataclass
from enum import Enum


class ErrorCode(str, Enum):
    """稳定错误代码，界面不得依赖异常文本判断错误类型。"""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_HEX = "INVALID_HEX"
    TEXT_ENCODING_ERROR = "TEXT_ENCODING_ERROR"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    BUFFER_CAPACITY_ERROR = "BUFFER_CAPACITY_ERROR"
    PORT_NOT_FOUND = "PORT_NOT_FOUND"
    PORT_BUSY = "PORT_BUSY"
    PORT_PERMISSION_DENIED = "PORT_PERMISSION_DENIED"
    TRANSPORT_IO_ERROR = "TRANSPORT_IO_ERROR"
    LOG_IO_ERROR = "LOG_IO_ERROR"
    CONFIG_IO_ERROR = "CONFIG_IO_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True, slots=True)
class UserFacingError:
    """可直接转换为用户提示的错误信息。"""

    code: ErrorCode
    message: str
    recoverable: bool
    suggestion: str | None = None
    diagnostic_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, ErrorCode):
            raise ValidationError("错误代码必须是 ErrorCode。")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValidationError("用户错误信息不能为空。")
        if type(self.recoverable) is not bool:
            raise ValidationError("recoverable 必须是布尔值。")
        if self.suggestion is not None and not isinstance(self.suggestion, str):
            raise ValidationError("suggestion 必须是字符串或 None。")
        if self.diagnostic_id is not None and not isinstance(self.diagnostic_id, str):
            raise ValidationError("diagnostic_id 必须是字符串或 None。")


class DomainError(Exception):
    """所有领域错误的基类。"""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    recoverable: bool = False
    default_message = "领域操作失败。"
    default_suggestion: str | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        suggestion: str | None = None,
        diagnostic_id: str | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.suggestion = suggestion if suggestion is not None else self.default_suggestion
        self.diagnostic_id = diagnostic_id
        super().__init__(self.message)

    def to_user_facing(self) -> UserFacingError:
        """转换为稳定的用户错误结构。"""
        return UserFacingError(
            code=self.code,
            message=self.message,
            recoverable=self.recoverable,
            suggestion=self.suggestion,
            diagnostic_id=self.diagnostic_id,
        )


class ValidationError(DomainError):
    """输入或领域不变量验证失败。"""

    code = ErrorCode.VALIDATION_ERROR
    recoverable = True
    default_message = "输入内容不符合要求。"
    default_suggestion = "请检查并修正输入后重试。"


class HexFormatError(ValidationError):
    """HEX 文本格式不合法。"""

    code = ErrorCode.INVALID_HEX
    default_message = "HEX 数据格式不合法。"
    default_suggestion = "请使用十六进制字节，例如 AA 01 FF。"


class TextEncodingError(ValidationError):
    """文本编码或解码失败。"""

    code = ErrorCode.TEXT_ENCODING_ERROR
    default_message = "文本编码或解码失败。"
    default_suggestion = "请确认当前字符编码与设备数据一致。"


class InvalidStateTransitionError(DomainError):
    """请求的会话状态转换不被允许。"""

    code = ErrorCode.INVALID_STATE_TRANSITION
    recoverable = True
    default_suggestion = "请刷新会话状态后重试。"

    def __init__(
        self,
        current_state: object,
        action: str,
        target_state: object | None = None,
    ) -> None:
        self.current_state = current_state
        self.action = action
        self.target_state = target_state
        current = getattr(current_state, "value", current_state)
        target = getattr(target_state, "value", target_state)
        target_text = f"到 {target}" if target is not None else ""
        super().__init__(f"当前状态 {current} 不允许执行 {action}{target_text}。")


class BufferCapacityError(DomainError):
    """单条记录超过缓冲区允许的最大字节数。"""

    code = ErrorCode.BUFFER_CAPACITY_ERROR
    recoverable = True
    default_message = "数据记录超过缓冲区容量限制。"


class PortNotFoundError(DomainError):
    """指定端口不存在。"""

    code = ErrorCode.PORT_NOT_FOUND
    recoverable = True
    default_message = "串口不存在或已被移除。"
    default_suggestion = "请检查设备连接后刷新端口列表。"


class PortBusyError(DomainError):
    """端口正被其他程序占用。"""

    code = ErrorCode.PORT_BUSY
    recoverable = True
    default_message = "串口正被其他程序占用。"
    default_suggestion = "请关闭占用端口的程序后重试。"


class PortPermissionError(DomainError):
    """当前用户没有访问端口的权限。"""

    code = ErrorCode.PORT_PERMISSION_DENIED
    recoverable = True
    default_message = "当前用户没有访问串口的权限。"
    default_suggestion = "请检查设备权限或用户所在系统用户组。"


class TransportIOError(DomainError):
    """串口读写失败。"""

    code = ErrorCode.TRANSPORT_IO_ERROR
    recoverable = True
    default_message = "串口通信失败。"
    default_suggestion = "请检查设备连接和串口参数。"


class LogIOError(DomainError):
    """日志写入失败。"""

    code = ErrorCode.LOG_IO_ERROR
    recoverable = True
    default_message = "日志写入失败。"
    default_suggestion = "请检查日志目录权限和可用磁盘空间。"


class ConfigIOError(DomainError):
    """配置读写失败。"""

    code = ErrorCode.CONFIG_IO_ERROR
    recoverable = True
    default_message = "配置读写失败。"
    default_suggestion = "请检查配置目录权限和可用磁盘空间。"


class InternalError(DomainError):
    """未预期的内部错误。"""

    code = ErrorCode.INTERNAL_ERROR
    recoverable = False
    default_message = "程序内部发生未预期错误。"
