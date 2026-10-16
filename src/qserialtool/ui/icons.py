"""动作按钮的矢量图标加载。"""

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QAbstractButton

from qserialtool.ui.style_sheet import assets_dir

# 按钮内动作图标的标准边长（像素）；颜色分“中性灰”与“白色”两档，由 SVG 自身决定。
ACTION_ICON_PX = 14


def svg_icon(name: str) -> QIcon:
    """按资源名加载矢量图标；资源缺失时 Qt 返回空图标而不是抛错。"""
    return QIcon(str(assets_dir() / f"{name}.svg"))


def set_action_icon(button: QAbstractButton, name: str) -> None:
    """给按钮设置动作图标，并按标准边长缩放。"""
    button.setIcon(svg_icon(name))
    button.setIconSize(QSize(ACTION_ICON_PX, ACTION_ICON_PX))
