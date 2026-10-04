"""加载应用窗口图标。"""

from PySide6.QtGui import QIcon

from .style_sheet import assets_dir


def app_icon() -> QIcon:
    """返回窗口与任务栏图标；资源缺失时 Qt 会给出空图标而不是抛错。"""
    return QIcon(str(assets_dir() / "qserialtool.png"))
