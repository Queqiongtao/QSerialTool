"""把 Worker 线程回调转换为 Qt 信号。"""

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot

from qserialtool.domain import LogRecord, SessionSnapshot

DEFAULT_SNAPSHOT_INTERVAL_MS = 50


class QtSessionBridge(QObject):
    """由工作线程发信号，由主线程接收会话事件。

    高频接收时 Worker 会按数据块发布快照；桥接层只把最新快照投递给 UI，
    首个快照立即生效，后续最多每 ``snapshot_interval_ms`` 合并一次，避免
    状态条和标签外观被无意义的字节计数刷新淹没。日志记录不参与合并。
    """

    snapshot_changed = Signal(object)
    record_received = Signal(object)
    _snapshot_arrived = Signal(object)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        snapshot_interval_ms: int = DEFAULT_SNAPSHOT_INTERVAL_MS,
    ) -> None:
        super().__init__(parent)
        if type(snapshot_interval_ms) is not int or snapshot_interval_ms <= 0:
            raise ValueError("快照合并间隔必须是正整数。")
        self._pending_snapshot: SessionSnapshot | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(snapshot_interval_ms)
        self._timer.timeout.connect(self._flush_snapshot)
        self._snapshot_arrived.connect(self._store_snapshot, Qt.ConnectionType.QueuedConnection)

    @Slot(object)
    def publish_snapshot(self, snapshot: SessionSnapshot) -> None:
        """从工作线程提交快照，由主线程合并后再通知 UI。"""
        self._snapshot_arrived.emit(snapshot)

    @Slot(object)
    def _store_snapshot(self, snapshot: SessionSnapshot) -> None:
        self._pending_snapshot = snapshot
        if not self._timer.isActive():
            self._flush_snapshot()
            self._timer.start()

    @Slot()
    def _flush_snapshot(self) -> None:
        snapshot = self._pending_snapshot
        self._pending_snapshot = None
        if snapshot is not None:
            self.snapshot_changed.emit(snapshot)

    @Slot(object)
    def publish_record(self, record: LogRecord) -> None:
        """发布不可变日志记录，记录不合并。"""
        self.record_received.emit(record)
