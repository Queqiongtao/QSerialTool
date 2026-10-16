"""数据区 Ctrl+滚轮的字号缩放事件过滤器。"""

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QWheelEvent


class FontZoomFilter(QObject):
    """把数据区的 Ctrl+滚轮转换为字号缩放请求（+1 放大、-1 缩小）。"""

    zoom_requested = Signal(int)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """拦截 Ctrl+滚轮并发出缩放请求，其余事件交给默认处理。"""
        if (
            event.type() == QEvent.Type.Wheel
            and isinstance(event, QWheelEvent)
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            delta = event.angleDelta().y() or event.angleDelta().x()
            if delta:
                self.zoom_requested.emit(1 if delta > 0 else -1)
                return True
        return super().eventFilter(watched, event)
