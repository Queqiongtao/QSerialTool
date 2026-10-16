"""窗口级空态引导：全部会话标签关闭后在内容区显示新建提示。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

# 空态文案：“+”按钮与 Ctrl+T 都是新建入口，F1 打开使用手册。
_TITLE = "还没有会话"
_HINT = (
    "点击标签栏的“+”，或按 Ctrl+T 新建会话；选择串口后点“连接”即可开始收发。按 F1 查看使用手册。"
)


def build_empty_state(parent: QWidget) -> QLabel:
    """创建内容区居中的空态提示标签（初始隐藏，由主窗口控制显隐与摆放）。"""
    label = QLabel(parent)
    # 与接收区“暂无数据”共用居中空态样式（见 style_qss.py 的 QLabel#emptyState）。
    label.setObjectName("emptyState")
    label.setText(f"<b>{_TITLE}</b><br><br>{_HINT}")
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    label.hide()
    return label
