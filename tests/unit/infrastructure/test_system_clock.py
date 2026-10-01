"""测试系统时钟适配。"""

from datetime import timezone

from qserialtool.infrastructure import SystemClock


def test_system_clock_returns_aware_utc_and_monotonic_values() -> None:
    clock = SystemClock()
    now = clock.now_utc()

    assert now.tzinfo is not None
    assert now.utcoffset() == timezone.utc.utcoffset(now)
    assert clock.monotonic() <= clock.monotonic()
