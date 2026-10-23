"""测试 QtSessionBridge 的快照合并与记录投递。"""

from qserialtool.ui.qt_bridge import QtSessionBridge


def test_bridge_coalesces_snapshots_and_keeps_latest(qtbot: object) -> None:
    bridge = QtSessionBridge(snapshot_interval_ms=200)
    received: list[object] = []
    bridge.snapshot_changed.connect(received.append)

    first = object()
    bridge.publish_snapshot(first)  # type: ignore[arg-type]
    qtbot.waitUntil(lambda: received == [first], timeout=1000)  # type: ignore[attr-defined]

    latest = object()
    for _ in range(3):
        bridge.publish_snapshot(object())  # type: ignore[arg-type]
    bridge.publish_snapshot(latest)  # type: ignore[arg-type]

    qtbot.waitUntil(lambda: len(received) == 2, timeout=2000)  # type: ignore[attr-defined]
    assert received[1] is latest


def test_bridge_publishes_every_record(qtbot: object) -> None:
    bridge = QtSessionBridge()
    received: list[object] = []
    bridge.record_received.connect(received.append)

    first = object()
    second = object()
    bridge.publish_record(first)  # type: ignore[arg-type]
    bridge.publish_record(second)  # type: ignore[arg-type]

    qtbot.waitUntil(lambda: received == [first, second], timeout=1000)  # type: ignore[attr-defined]
