"""测试记录缓冲的数量和字节淘汰规则。"""

from datetime import datetime, timezone
from typing import cast

import pytest

from qserialtool.domain import BufferCapacityError, LogRecord, RecordBuffer


def _record(raw: bytes) -> LogRecord:
    return LogRecord.from_bytes(
        timestamp_utc=datetime.now(timezone.utc),
        direction="rx",
        raw=raw,
        encoding="utf-8",
        session_id="session-1",
    )


def test_buffer_evicts_oldest_record_when_count_limit_is_exceeded() -> None:
    buffer = RecordBuffer(max_records=2, max_bytes=100)
    first = _record(b"1")
    second = _record(b"2")
    third = _record(b"3")

    assert buffer.append(first) == 0
    assert buffer.append(second) == 0
    assert buffer.append(third) == 1
    assert buffer.records == (second, third)
    assert buffer.dropped_records == 1


def test_buffer_evicts_records_when_byte_limit_is_exceeded() -> None:
    buffer = RecordBuffer(max_records=100, max_bytes=5)
    records = [_record(bytes([value]) * 2) for value in range(4)]

    assert buffer.append(records[0]) == 0
    assert buffer.append(records[1]) == 0
    assert buffer.append(records[2]) == 1
    assert buffer.record_count == 2
    assert buffer.byte_size == 4
    assert buffer.dropped_records == 1


def test_buffer_rejects_single_record_larger_than_byte_limit() -> None:
    buffer = RecordBuffer(max_records=10, max_bytes=2)
    with pytest.raises(BufferCapacityError):
        buffer.append(_record(b"abc"))


@pytest.mark.parametrize(("max_records", "max_bytes"), [(0, 1), (1, 0), (True, 1), (1, True)])
def test_buffer_rejects_invalid_limits(max_records: int, max_bytes: int) -> None:
    with pytest.raises(ValueError):
        RecordBuffer(max_records=max_records, max_bytes=max_bytes)


def test_buffer_clear_preserves_dropped_counter() -> None:
    buffer = RecordBuffer(max_records=1, max_bytes=100)
    buffer.append(_record(b"1"))
    buffer.append(_record(b"2"))

    assert buffer.clear() == 1
    assert buffer.records == ()
    assert buffer.byte_size == 0
    assert buffer.dropped_records == 1


def test_buffer_records_property_returns_immutable_snapshot() -> None:
    buffer = RecordBuffer(max_records=2, max_bytes=100)
    record = _record(b"1")
    buffer.append(record)

    snapshot = buffer.records
    assert snapshot == (record,)
    assert isinstance(snapshot, tuple)


def test_buffer_rejects_non_record_values() -> None:
    buffer = RecordBuffer()
    with pytest.raises(BufferCapacityError):
        buffer.append(cast(LogRecord, object()))
