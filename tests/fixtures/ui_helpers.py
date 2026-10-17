"""主窗口测试的装配助手与文档片段检查工具。"""

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QFont, QMouseEvent, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from qserialtool.application import SessionManager
from qserialtool.domain import PortInfo, SessionState
from qserialtool.ui import MainWindow, SessionTab
from qserialtool.ui.terminal_output import TerminalOutput
from tests.fixtures.fakes import FakeClock, FakeTransport


def build_window(qtbot: object, transport: FakeTransport) -> MainWindow:
    manager = SessionManager(
        transport_factory=lambda: transport,
        clock=FakeClock(),
    )
    window = MainWindow(
        session_manager=manager,
        port_provider=lambda: (PortInfo(device="COM1"),),
    )
    qtbot.addWidget(window)
    window.show()
    return window


def current_tab(window: MainWindow) -> SessionTab:
    tab = window.tabs.currentWidget()
    assert isinstance(tab, SessionTab)
    return tab


def connect_session(qtbot: object, tab: SessionTab) -> None:
    tab.connection_panel.port_combo.setEditText("COM1")
    tab.connection_panel.baud_combo.setEditText("9600")
    qtbot.mouseClick(tab.connection_panel.connect_button, Qt.MouseButton.LeftButton)
    # 快照经队列连接异步送达；必须等 UI 真正应用了 CONNECTED（发送按钮启用），
    # 否则后续断言可能撞上尚未更新的连接状态。
    qtbot.waitUntil(
        lambda: (
            tab.controller.state is SessionState.CONNECTED
            and not tab.connection_panel.port_combo.isEnabled()
            and tab.send_panel.send_button.isEnabled()
        ),
        timeout=2000,
    )


def disconnect_session(qtbot: object, tab: SessionTab) -> None:
    if tab.controller.state is SessionState.CONNECTED:
        qtbot.mouseClick(tab.connection_panel.connect_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(
            lambda: tab.controller.state is SessionState.DISCONNECTED,
            timeout=2000,
        )


class RecordingStore:
    """记录每次保存的配置，用于验证空闲状态不会重复写盘。"""

    def __init__(self) -> None:
        self.saves: list[object] = []

    def load(self) -> None:
        return None

    def save(self, config: object) -> None:
        self.saves.append(config)


def build_window_with_store(
    qtbot: object,
    transport: FakeTransport,
    store: RecordingStore,
) -> MainWindow:
    manager = SessionManager(
        transport_factory=lambda: transport,
        clock=FakeClock(),
    )
    window = MainWindow(
        session_manager=manager,
        port_provider=lambda: (PortInfo(device="COM1"), PortInfo(device="COM2")),
        config_store=store,
    )
    qtbot.addWidget(window)
    window.show()
    return window


def build_window_with_ports(
    qtbot: object,
    transport: FakeTransport,
    ports: tuple[PortInfo, ...],
) -> MainWindow:
    manager = SessionManager(
        transport_factory=lambda: transport,
        clock=FakeClock(),
    )
    window = MainWindow(
        session_manager=manager,
        port_provider=lambda: ports,
    )
    qtbot.addWidget(window)
    window.show()
    return window


def fragment_formats(output: TerminalOutput) -> list[tuple[str, str]]:
    """按顺序返回文档片段的 (文本, 前景色)，用于断言渲染配色。"""
    formats: list[tuple[str, str]] = []
    block = output.document().firstBlock()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment is not None and fragment.text():
                color = fragment.charFormat().foreground().color().name()
                formats.append((fragment.text(), color))
            iterator += 1
        block = block.next()
    return formats


def fragment_styles(output: TerminalOutput) -> list[tuple[str, str, bool]]:
    """按顺序返回文档片段的 (文本, 前景色, 是否加粗)，用于断言分层配色。"""
    styles: list[tuple[str, str, bool]] = []
    block = output.document().firstBlock()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment is not None and fragment.text():
                char_format = fragment.charFormat()
                styles.append(
                    (
                        fragment.text(),
                        char_format.foreground().color().name(),
                        char_format.fontWeight() >= QFont.Weight.Bold,
                    )
                )
            iterator += 1
        block = block.next()
    return styles


def cursor_point(output: TerminalOutput, position: int) -> QPoint:
    """返回文档字符位置在视口中的中心点，供模拟鼠标交互使用。"""
    cursor = QTextCursor(output.document())
    cursor.setPosition(position)
    return output.cursorRect(cursor).center()


def mouse_press(output: TerminalOutput, pos: QPoint) -> None:
    """在接收区模拟左键按下。"""
    QTest.mousePress(output.viewport(), Qt.MouseButton.LeftButton, pos=pos)


def mouse_drag(output: TerminalOutput, pos: QPoint) -> None:
    """模拟按住左键拖到 pos。

    ``QTest.mouseMove`` 携带的按键状态为空，文本控件不会据此扩展选区，
    因此自建带左键的移动事件。
    """
    viewport = output.viewport()
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(pos),
        QPointF(viewport.mapToGlobal(pos)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(viewport, event)


def mouse_release(output: TerminalOutput, pos: QPoint) -> None:
    """在接收区模拟左键释放。"""
    QTest.mouseRelease(output.viewport(), Qt.MouseButton.LeftButton, pos=pos)
