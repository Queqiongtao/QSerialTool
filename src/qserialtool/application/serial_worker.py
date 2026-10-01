"""串口工作线程的命令队列和 I/O 循环。"""

from collections.abc import Callable
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from typing import Protocol

from qserialtool.domain import (
    DomainError,
    InternalError,
    SendQueueFullError,
    SerialConfig,
    Transport,
    TransportIOError,
    ValidationError,
)

DEFAULT_READ_TIMEOUT = 0.05
DEFAULT_READ_CHUNK_SIZE = 8192
DEFAULT_WRITE_QUEUE_SIZE = 256
DEFAULT_CLOSE_TIMEOUT = 1.0


@dataclass(frozen=True, slots=True)
class SerialWorkerOptions:
    """SerialWorker 的读取、队列和关闭参数。"""

    read_timeout: float = DEFAULT_READ_TIMEOUT
    read_chunk_size: int = DEFAULT_READ_CHUNK_SIZE
    write_queue_size: int = DEFAULT_WRITE_QUEUE_SIZE
    close_timeout: float = DEFAULT_CLOSE_TIMEOUT

    def __post_init__(self) -> None:
        if self.read_timeout <= 0:
            raise ValidationError("读取超时必须大于零。")
        if type(self.read_chunk_size) is not int or self.read_chunk_size <= 0:
            raise ValidationError("读取块大小必须是正整数。")
        if type(self.write_queue_size) is not int or self.write_queue_size <= 0:
            raise ValidationError("发送队列大小必须是正整数。")
        if self.close_timeout <= 0:
            raise ValidationError("关闭超时必须大于零。")


class WorkerEventHandler(Protocol):
    """接收 Worker 线程事件；实现方必须保证方法可跨线程调用。"""

    def on_opened(self, config: SerialConfig) -> None:
        """串口打开成功。"""
        ...

    def on_open_failed(self, error: DomainError) -> None:
        """串口打开失败。"""
        ...

    def on_bytes_received(self, data: bytes) -> None:
        """收到串口数据。"""
        ...

    def on_bytes_sent(self, data: bytes) -> None:
        """完成一次串口写入。"""
        ...

    def on_io_error(self, error: DomainError) -> None:
        """读取、写入或线路控制失败。"""
        ...

    def on_stopped(self) -> None:
        """Worker 已结束并完成资源清理。"""
        ...


@dataclass(frozen=True, slots=True)
class _SetLineStateCommand:
    dtr: bool
    rts: bool


@dataclass(frozen=True, slots=True)
class _WriteCommand:
    data: bytes


class SerialWorker:
    """独占指定 Transport，并在独立线程中处理命令和读取数据。"""

    def __init__(
        self,
        *,
        config: SerialConfig,
        transport_factory: Callable[[], Transport],
        event_handler: WorkerEventHandler,
        options: SerialWorkerOptions | None = None,
    ) -> None:
        if not callable(transport_factory):
            raise ValidationError("transport_factory 必须可调用。")
        selected_options = options or SerialWorkerOptions()
        self._config = config
        self._transport_factory = transport_factory

        self._event_handler = event_handler
        self._read_timeout = selected_options.read_timeout
        self._read_chunk_size = selected_options.read_chunk_size
        self._close_timeout = selected_options.close_timeout
        self._control_queue: Queue[_SetLineStateCommand] = Queue()
        self._write_queue: Queue[_WriteCommand] = Queue(maxsize=selected_options.write_queue_size)
        self._stop_requested = Event()
        self._start_lock = Lock()
        self._thread: Thread | None = None

    @property
    def is_alive(self) -> bool:
        """返回工作线程是否仍在运行。"""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """启动工作线程，每个 Worker 只能启动一次。"""
        with self._start_lock:
            if self._thread is not None:
                raise ValidationError("Worker 已经启动。")
            self._thread = Thread(target=self._run, name="qserialtool-serial-worker", daemon=False)
            self._thread.start()

    def join(self, timeout: float | None = None) -> bool:
        """等待工作线程结束。"""
        if self._thread is None:
            return True
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def request_stop(self) -> None:
        """请求 Worker 安全停止。"""
        self._stop_requested.set()

    def send(self, data: bytes) -> None:
        """将完整写入任务加入有界发送队列。"""
        if not isinstance(data, bytes) or not data:
            raise ValidationError("待发送数据必须是非空 bytes。")
        try:
            self._write_queue.put_nowait(_WriteCommand(data=data))
        except Full as exc:
            raise SendQueueFullError("发送队列已满，请等待当前数据发送完成。") from exc

    def set_line_state(self, *, dtr: bool, rts: bool) -> None:
        """将 DTR/RTS 控制加入控制队列。"""
        if type(dtr) is not bool or type(rts) is not bool:
            raise ValidationError("DTR 和 RTS 必须是布尔值。")
        self._control_queue.put(_SetLineStateCommand(dtr=dtr, rts=rts))

    def _run(self) -> None:
        transport: Transport | None = None
        opened = False
        try:
            try:
                transport = self._transport_factory()
                transport.open(self._config)
            except DomainError as exc:
                self._event_handler.on_open_failed(exc)
                return
            except Exception as exc:
                self._event_handler.on_open_failed(
                    InternalError(f"打开串口时发生未预期错误：{exc}")
                )
                return

            opened = True
            self._event_handler.on_opened(self._config)
            while not self._stop_requested.is_set():
                if not self._process_control_commands(transport):
                    break
                self._process_one_write(transport)
                if not transport.is_open:
                    self._event_handler.on_io_error(TransportIOError("串口已关闭。"))
                    break
                self._read_once(transport)
        finally:
            if opened:
                self._close_transport(transport)
            self._event_handler.on_stopped()

    def _process_control_commands(self, transport: Transport) -> bool:
        while True:
            try:
                command = self._control_queue.get_nowait()
            except Empty:
                return True
            try:
                transport.set_line_state(dtr=command.dtr, rts=command.rts)
            except DomainError as exc:
                self._event_handler.on_io_error(exc)
                return False
            except Exception as exc:
                self._event_handler.on_io_error(InternalError(f"设置线路状态失败：{exc}"))
                return False

    def _process_one_write(self, transport: Transport) -> None:
        try:
            command = self._write_queue.get_nowait()
        except Empty:
            return
        try:
            transport.write_all(command.data, timeout=1.0)
        except DomainError as exc:
            self._event_handler.on_io_error(exc)
            self._stop_requested.set()
            return
        except Exception as exc:
            self._event_handler.on_io_error(InternalError(f"写入串口时发生未预期错误：{exc}"))
            self._stop_requested.set()
            return
        self._event_handler.on_bytes_sent(command.data)

    def _read_once(self, transport: Transport) -> None:
        try:
            data = transport.read(self._read_chunk_size, timeout=self._read_timeout)
        except DomainError as exc:
            self._event_handler.on_io_error(exc)
            self._stop_requested.set()
            return
        except Exception as exc:
            self._event_handler.on_io_error(InternalError(f"读取串口时发生未预期错误：{exc}"))
            self._stop_requested.set()
            return
        if data:
            self._event_handler.on_bytes_received(data)

    def _close_transport(self, transport: Transport) -> None:
        if not transport.is_open:
            return
        try:
            transport.close(self._close_timeout)
        except DomainError as exc:
            self._event_handler.on_io_error(exc)
        except Exception as exc:
            self._event_handler.on_io_error(InternalError(f"关闭串口时发生未预期错误：{exc}"))
