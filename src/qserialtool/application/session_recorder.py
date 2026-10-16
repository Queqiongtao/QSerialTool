"""单会话的接收缓冲、收发计数与流式记录构造。"""

from qserialtool.domain import (
    Clock,
    EncodingName,
    LogRecord,
    RecordBuffer,
    decode_partial,
)


class SessionRecorder:
    """维护内存缓冲、RX/TX 累计字节与跨读取块的解码尾巴。

    所有方法都假定由持有会话锁的调用方调用，自身不加锁。
    """

    def __init__(self, *, buffer: RecordBuffer, clock: Clock, session_id: str) -> None:
        self._buffer = buffer
        self._clock = clock
        self._session_id = session_id
        self._rx_tail = b""
        self._rx_bytes = 0
        self._tx_bytes = 0

    @property
    def records(self) -> tuple[LogRecord, ...]:
        """返回当前内存缓冲的不可变快照。"""
        return self._buffer.records

    @property
    def rx_bytes(self) -> int:
        """返回累计接收字节数。"""
        return self._rx_bytes

    @property
    def tx_bytes(self) -> int:
        """返回累计发送字节数。"""
        return self._tx_bytes

    @property
    def dropped_records(self) -> int:
        """返回因缓冲上限被淘汰的记录数。"""
        return self._buffer.dropped_records

    def append(self, record: LogRecord) -> None:
        """把记录追加到内存缓冲。"""
        self._buffer.append(record)

    def clear_buffer(self) -> int:
        """清空内存缓冲但不重置累计统计。"""
        return self._buffer.clear()

    def on_received(self, data: bytes, encoding: EncodingName) -> LogRecord | None:
        """拼接跨读取块的不完整多字节字符；返回本次可入缓冲的记录。"""
        combined = self._rx_tail + data
        text, self._rx_tail = decode_partial(combined, encoding)
        self._rx_bytes += len(data)
        if not text:
            return None
        return LogRecord.from_bytes(
            timestamp_utc=self._clock.now_utc(),
            direction="rx",
            raw=combined[: len(combined) - len(self._rx_tail)],
            encoding=encoding,
            session_id=self._session_id,
            text=text,
        )

    def on_sent(self, data: bytes, encoding: EncodingName) -> LogRecord:
        """构造发送完成记录并累计 TX 字节。"""
        self._tx_bytes += len(data)
        return LogRecord.from_bytes(
            timestamp_utc=self._clock.now_utc(),
            direction="tx",
            raw=data,
            encoding=encoding,
            session_id=self._session_id,
        )

    def flush_tail(self, encoding: EncodingName) -> LogRecord | None:
        """把未成形的尾字节按占位文本构造成接收记录，并清空尾巴。"""
        if not self._rx_tail:
            return None
        tail = self._rx_tail
        self._rx_tail = b""
        return LogRecord.from_bytes(
            timestamp_utc=self._clock.now_utc(),
            direction="rx",
            raw=tail,
            encoding=encoding,
            session_id=self._session_id,
        )

    def reset_tail(self) -> None:
        """清空跨读取块的解码尾巴（连接开始时调用）。"""
        self._rx_tail = b""

    def system_record(self, message: str) -> LogRecord:
        """构造一条系统事件记录。"""
        raw = message.encode("utf-8")
        return LogRecord.from_bytes(
            timestamp_utc=self._clock.now_utc(),
            direction="system",
            raw=raw,
            encoding="utf-8",
            session_id=self._session_id,
        )
