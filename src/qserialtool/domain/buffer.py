"""有界的串口记录缓冲。"""

from collections import deque
from dataclasses import dataclass, field

from .errors import BufferCapacityError
from .models import LogRecord

DEFAULT_MAX_RECORDS = 100_000
DEFAULT_MAX_BYTES = 32 * 1024 * 1024


@dataclass(slots=True)
class RecordBuffer:
    """按记录数和原始字节数共同限制内存。"""

    max_records: int = DEFAULT_MAX_RECORDS
    max_bytes: int = DEFAULT_MAX_BYTES
    _records: deque[LogRecord] = field(init=False, repr=False)
    _byte_size: int = field(init=False, default=0, repr=False)
    _dropped_records: int = field(init=False, default=0, repr=False)

    def __post_init__(self) -> None:
        if type(self.max_records) is not int or self.max_records <= 0:
            raise ValueError("max_records 必须是正整数。")
        if type(self.max_bytes) is not int or self.max_bytes <= 0:
            raise ValueError("max_bytes 必须是正整数。")
        self._records = deque()

    @property
    def records(self) -> tuple[LogRecord, ...]:
        """返回当前记录的不可变快照。"""
        return tuple(self._records)

    @property
    def record_count(self) -> int:
        """返回当前记录数量。"""
        return len(self._records)

    @property
    def byte_size(self) -> int:
        """返回当前原始字节总数。"""
        return self._byte_size

    @property
    def dropped_records(self) -> int:
        """返回缓冲区生命周期内累计淘汰的记录数。"""
        return self._dropped_records

    def append(self, record: LogRecord) -> int:
        """追加记录并返回本次淘汰的记录数。"""
        if not isinstance(record, LogRecord):
            raise BufferCapacityError("缓冲区只能追加 LogRecord。")
        record_size = len(record.raw)
        if record_size > self.max_bytes:
            raise BufferCapacityError("单条记录超过缓冲区字节上限。")
        self._records.append(record)
        self._byte_size += record_size
        dropped = 0
        while len(self._records) > self.max_records or self._byte_size > self.max_bytes:
            removed = self._records.popleft()
            self._byte_size -= len(removed.raw)
            dropped += 1
        self._dropped_records += dropped
        return dropped

    def clear(self) -> int:
        """清空当前记录并返回移除数量，不重置累计丢弃计数。"""
        removed = len(self._records)
        self._records.clear()
        self._byte_size = 0
        return removed
