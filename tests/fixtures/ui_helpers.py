"""主窗口测试的装配助手与文档片段检查工具。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

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
    qtbot.waitUntil(
        lambda: (
            tab.controller.state is SessionState.CONNECTED
            and not tab.connection_panel.port_combo.isEnabled()
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
