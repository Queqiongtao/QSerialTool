"""窗口级空态引导：全部会话标签关闭后在内容区显示新建提示。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

# 文案里“新建会话”链接的 href；标签栏“+”、Ctrl+T 与它都是新建入口，F1 打开使用手册。
NEW_SESSION_HREF = "new-session"
_TITLE = "还没有会话"
_HINT = (
    f'点击<a href="{NEW_SESSION_HREF}">新建会话</a>，或点标签栏的“+”、按 Ctrl+T；'
    "选择串口后点“连接”即可开始收发。按 F1 查看使用手册。"
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
    # 窗口级空态不设 WA_TransparentForMouseEvents：文案里的“新建会话”链接要接收点击，
    # 而无会话时内容区本来就没有需要鼠标穿透的控件；链接颜色走调色板 Link 角色
    # （theme_manager 用 accent 令牌填充，两套主题都满足对比度）。接收区“暂无数据”
    # 空态覆盖在有内容的视口上，仍保持鼠标穿透。
    label.hide()
    return label


def refresh_empty_state(label: QLabel) -> None:
    """主题切换后重建富文本文案，让链接按新主题的强调色重新解析。

    链接颜色在富文本解析时固化进字符格式，仅刷新样式表不会更新；QLabel 对
    相同文本会短路，必须先清空再设回才能触发重新解析。
    """
    text = label.text()
    label.setText("")
    label.setText(text)
