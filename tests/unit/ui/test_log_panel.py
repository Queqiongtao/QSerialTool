"""测试日志面板长路径状态文本的省略显示。"""

from tests.fixtures.fakes import FakeClock, FakeTransport

from qserialtool.application import SessionController, SessionControllerOptions
from qserialtool.domain import SerialConfig
from qserialtool.ui import LogPanel

_LONG_STATUS = (
    "日志：C:\\Users\\tester\\Documents\\QSerialTool\\Logs\\QSerialTool_COM1_20261002_101010.csv"
)


def _controller() -> SessionController:
    transport = FakeTransport()
    return SessionController(
        config=SerialConfig(port="COM1"),
        transport_factory=lambda: transport,
        clock=FakeClock(),
        options=SessionControllerOptions(session_id="log-panel"),
    )


def test_log_panel_elides_long_status_text(qtbot: object) -> None:
    controller = _controller()
    panel = LogPanel(controller=controller)
    qtbot.addWidget(panel)

    try:
        panel.show()
        panel.resize(220, 160)
        panel._set_status(_LONG_STATUS)

        qtbot.waitUntil(lambda: "…" in panel.status_label.text(), timeout=2000)

        assert panel.status_label.text() != _LONG_STATUS
        assert panel.status_label.toolTip() == _LONG_STATUS
    finally:
        controller.close(force=True)


def test_log_panel_directory_row_layout(qtbot: object) -> None:
    controller = _controller()
    panel = LogPanel(controller=controller)
    qtbot.addWidget(panel)

    try:
        panel.show()
        panel.resize(272, 200)
        qtbot.wait(50)

        # 面板必须能塞进侧栏最小宽度，否则路径和按钮会被右侧裁掉。
        assert panel.minimumSizeHint().width() <= 260
        # 路径独占一行并铺满内容宽度；“选择目录/打开目录”等宽，“导出”独占整行。
        content_right = panel.export_button.geometry().right()
        assert panel.directory_edit.geometry().right() == content_right
        assert panel.browse_button.width() == panel.open_button.width()
        assert panel.export_button.width() > panel.browse_button.width()
    finally:
        controller.close(force=True)
