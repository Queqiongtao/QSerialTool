"""关于对话框。"""

import platform

from PySide6.QtCore import Qt, QUrl, qVersion
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qserialtool import __version__
from qserialtool.ui.app_icon import app_icon

_AUTHOR = "Queqiongtao"
_REPOSITORY_URL = "https://github.com/Queqiongtao/QSerialTool"
_REPOSITORY_LABEL = "Queqiongtao/QSerialTool"
_THIRD_PARTY_URL = f"{_REPOSITORY_URL}/blob/main/THIRD_PARTY_NOTICES.md"
_LICENSE_LABEL = "© 2026 QSerialTool contributors · MIT License"
_ICON_PIXEL_SIZE = 64


class AboutDialog(QDialog):
    """展示版本、作者、运行环境与许可证信息的非模态对话框。

    源码仓库和第三方组件声明通过 ``linkActivated`` 转交系统浏览器打开而不是
    ``setOpenExternalLinks(True)``，以便单元测试替换 ``QDesktopServices``。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("关于 QSerialTool")
        self.setWindowIcon(app_icon())

        self.icon_label = QLabel()
        self.icon_label.setPixmap(app_icon().pixmap(_ICON_PIXEL_SIZE, _ICON_PIXEL_SIZE))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.title_label = QLabel("QSerialTool")
        title_font = self.title_label.font()
        title_font.setBold(True)
        if title_font.pointSize() > 0:
            title_font.setPointSize(title_font.pointSize() + 2)
        self.title_label.setFont(title_font)

        self.version_label = QLabel(f"版本：{__version__}")
        self.author_label = QLabel(f"作者：{_AUTHOR}")
        self.environment_label = QLabel(
            f"运行环境：Python {platform.python_version()} · Qt {qVersion()}"
        )
        self.license_label = QLabel(f"版权：{_LICENSE_LABEL}")

        self.repository_label = self._link_label(
            f'GitHub：<a href="{_REPOSITORY_URL}">{_REPOSITORY_LABEL}</a>', _REPOSITORY_URL
        )
        self.third_party_label = self._link_label(
            f'<a href="{_THIRD_PARTY_URL}">第三方组件声明</a>', _THIRD_PARTY_URL
        )

        for label in (
            self.title_label,
            self.version_label,
            self.author_label,
            self.environment_label,
            self.license_label,
        ):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(6)
        for widget in (
            self.title_label,
            self.version_label,
            self.author_label,
            self.repository_label,
            self.third_party_label,
            self.environment_label,
            self.license_label,
        ):
            info_layout.addWidget(widget)
        info_layout.addStretch(1)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)
        body.addLayout(info_layout, 1)

        self.close_button = QPushButton("关闭")
        self.close_button.setAutoDefault(False)
        self.close_button.clicked.connect(self.close)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(self.close_button)

        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addLayout(footer)
        # 按内容取固定尺寸，避免硬编码尺寸在系统字体变化时裁掉文字。
        self.setFixedSize(self.sizeHint())

    def _link_label(self, html: str, tooltip: str) -> QLabel:
        """构造带主题色超链接的标签，点击后交给系统浏览器。"""
        label = QLabel()
        label.setText(html)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        label.setToolTip(tooltip)
        label.linkActivated.connect(self._open_link)
        return label

    def _open_link(self, url: str) -> None:
        """在系统默认浏览器中打开链接，地址来自富文本锚点。"""
        QDesktopServices.openUrl(QUrl(url))
