"""动作按钮的矢量图标加载与标签页状态圆点绘制。"""

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractButton

from qserialtool.domain import SessionState
from qserialtool.ui.style_sheet import assets_dir
from qserialtool.ui.theme_manager import data_colors, resolved_theme

# 按钮内动作图标的标准边长（像素）；颜色分“中性灰”与“白色”两档，由 SVG 自身决定。
ACTION_ICON_PX = 14

# 标签页状态圆点：画布边长与圆点半径（像素）。
_STATE_ICON_PX = 14
_STATE_DOT_RADIUS = 4.0

# （状态值, 主题）→ 圆点图标；取值空间最多 6 状态 × 2 主题，不需要淘汰策略。
_STATE_ICON_CACHE: dict[tuple[str, str], QIcon] = {}


def svg_icon(name: str) -> QIcon:
    """按资源名加载矢量图标；资源缺失时 Qt 返回空图标而不是抛错。"""
    return QIcon(str(assets_dir() / f"{name}.svg"))


def set_action_icon(button: QAbstractButton, name: str) -> None:
    """给按钮设置动作图标，并按标准边长缩放。"""
    button.setIcon(svg_icon(name))
    button.setIconSize(QSize(ACTION_ICON_PX, ACTION_ICON_PX))


def state_icon(state: SessionState) -> QIcon:
    """按会话状态与当前主题绘制实心圆点图标。

    多标签并行时标签栏直接显示连接状态；颜色取 ``data_colors()`` 的状态色，
    与底部状态条圆点保持一致。按（状态值, 主题）缓存光栅化结果。
    """
    key = (state.value, resolved_theme())
    cached = _STATE_ICON_CACHE.get(key)
    if cached is None:
        cached = QIcon(_render_state_dot(_state_color(state)))
        _STATE_ICON_CACHE[key] = cached
    return cached


def _state_color(state: SessionState) -> str:
    """把状态映射为数据区状态色，语义与 StatusStrip 一致。"""
    colors = data_colors()
    if state is SessionState.CONNECTED:
        return colors.connected
    if state is SessionState.ERROR:
        return colors.error
    if state in {SessionState.CONNECTING, SessionState.DISCONNECTING}:
        return colors.pending
    return colors.idle


def _render_state_dot(color: str) -> QPixmap:
    """在透明画布上绘制居中的抗锯齿实心圆点。"""
    pixmap = QPixmap(_STATE_ICON_PX, _STATE_ICON_PX)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    center = _STATE_ICON_PX / 2
    painter.drawEllipse(QPointF(center, center), _STATE_DOT_RADIUS, _STATE_DOT_RADIUS)
    painter.end()
    return pixmap
