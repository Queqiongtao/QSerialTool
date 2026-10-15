"""测试日志面板长路径状态文本的省略显示与导出默认路径。"""

from pathlib import Path

from tests.fixtures.fakes import FakeClock, FakeTransport

from qserialtool.application import (
    SessionController,
    SessionControllerOptions,
    default_log_directory,
)
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


def test_log_panel_export_default_path_uses_directory(
    qtbot: object,
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    controller = _controller()
    panel = LogPanel(controller=controller)
    qtbot.addWidget(panel)
    directories: list[str] = []

    class _FakeFileDialog:
        @staticmethod
        def getSaveFileName(
            parent: object, title: str, directory: str, filters: str
        ) -> tuple[str, str]:
            directories.append(directory)
            return "", ""

    monkeypatch.setattr("qserialtool.ui.log_panel.QFileDialog", _FakeFileDialog)
    try:
        panel.directory_edit.setText(str(tmp_path / "logs"))
        panel._export()

        assert directories == [str(tmp_path / "logs" / "QSerialTool_export.csv")]

        panel.directory_edit.setText("   ")
        panel._export()

        assert directories[-1] == str(default_log_directory() / "QSerialTool_export.csv")
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
