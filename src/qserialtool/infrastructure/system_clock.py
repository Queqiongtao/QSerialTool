"""基于系统时钟的 Clock 实现。"""

from datetime import datetime, timezone
from time import monotonic


class SystemClock:
    """提供 UTC 时间和单调秒数。"""

    def now_utc(self) -> datetime:
        """返回包含 UTC 时区的当前时间。"""
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        """返回系统单调时钟秒数。"""
        return monotonic()
