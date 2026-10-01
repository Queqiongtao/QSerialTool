"""把 Worker 线程回调转换为 Qt 信号。"""

from PySide6.QtCore import QObject, Signal, Slot

from qserialtool.domain import LogRecord, SessionSnapshot


class QtSessionBridge(QObject):
    """由工作线程发信号，由主线程接收会话事件。"""

    snapshot_changed = Signal(object)
    record_received = Signal(object)

    @Slot(object)
    def publish_snapshot(self, snapshot: SessionSnapshot) -> None:
        """发布不可变快照。"""
        self.snapshot_changed.emit(snapshot)

    @Slot(object)
    def publish_record(self, record: LogRecord) -> None:
        """发布不可变日志记录。"""
        self.record_received.emit(record)
