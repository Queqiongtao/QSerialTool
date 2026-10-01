"""串口会话状态。"""

from enum import Enum


class SessionState(str, Enum):
    """会话状态机可处于的稳定状态。"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    ERROR = "error"
    CLOSED = "closed"

    def __str__(self) -> str:
        """返回适合日志和展示的稳定字符串值。"""
        return self.value
