"""关于对话框。"""

from PySide6.QtCore import Qt, QUrl
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
_ICON_PIXEL_SIZE = 64


class AboutDialog(QDialog):
    """展示版本、作者与源码仓库链接的非模态对话框。

    GitHub 链接通过 ``linkActivated`` 转交系统浏览器打开而不是
    ``setOpenExternalLinks(True)``，以便单元测试替换 ``QDesktopServices``。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("关于 QSerialTool")
        self.setWindowIcon(app_icon())
        self.setFixedSize(400, 200)

        self.icon_label = QLabel()
        self.icon_label.setPixmap(app_icon().pixmap(_ICON_PIXEL_SIZE, _ICON_PIXEL_SIZE))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.title_label = QLabel(f"QSerialTool {__version__}")
        title_font = self.title_label.font()
        title_font.setBold(True)
        if title_font.pointSize() > 0:
            title_font.setPointSize(title_font.pointSize() + 2)
        self.title_label.setFont(title_font)

        self.author_label = QLabel(f"作者：{_AUTHOR}")

        self.repository_label = QLabel()
        self.repository_label.setText(
            f'GitHub：<a href="{_REPOSITORY_URL}">{_REPOSITORY_LABEL}</a>'
        )
        self.repository_label.setTextFormat(Qt.TextFormat.RichText)
        self.repository_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        self.repository_label.setToolTip(_REPOSITORY_URL)
        self.repository_label.linkActivated.connect(self._open_repository)

        for label in (self.title_label, self.author_label):
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(6)
        info_layout.addWidget(self.title_label)
        info_layout.addWidget(self.author_label)
        info_layout.addWidget(self.repository_label)
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

    def _open_repository(self, url: str) -> None:
        """在系统默认浏览器中打开源码仓库，链接地址来自富文本锚点。"""
        QDesktopServices.openUrl(QUrl(url))
