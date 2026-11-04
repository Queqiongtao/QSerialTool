"""测试启动入口的桌面文件声明。"""

from PySide6.QtWidgets import QApplication

from qserialtool.bootstrap.app import DESKTOP_FILE_NAME, configure_desktop_entry


def test_configure_desktop_entry_declares_desktop_file_name(qapp: QApplication) -> None:
    configure_desktop_entry(qapp)
    assert qapp.desktopFileName() == DESKTOP_FILE_NAME == "qserialtool"
