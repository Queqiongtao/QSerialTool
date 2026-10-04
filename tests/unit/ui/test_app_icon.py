"""校验应用图标资源可加载。"""

from PySide6.QtWidgets import QApplication

from qserialtool.ui.app_icon import app_icon
from qserialtool.ui.style_sheet import assets_dir


def test_icon_assets_exist() -> None:
    assert (assets_dir() / "qserialtool.png").is_file()
    assert (assets_dir() / "qserialtool.ico").is_file()


def test_app_icon_renders(qapp: QApplication) -> None:
    icon = app_icon()
    assert not icon.isNull()
    assert not icon.pixmap(256, 256).isNull()
