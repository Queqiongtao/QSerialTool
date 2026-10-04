"""使用帮助窗口。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QListWidget,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from qserialtool.ui.app_icon import app_icon
from qserialtool.ui.style_sheet import assets_dir

_HELP_FILE_NAME = "user-guide.md"
_TOC_HEADING_LEVEL = 2
_FALLBACK_TEXT = "未能加载内置使用手册，请重新安装，或在源码仓库中查看 docs/user-guide.md。"


def _collect_sections(document: QTextDocument) -> list[tuple[str, int]]:
    """返回文档中所有二级标题的（标题，起始位置）。"""
    sections: list[tuple[str, int]] = []
    block = document.begin()
    while block.isValid():
        if block.blockFormat().headingLevel() == _TOC_HEADING_LEVEL:
            sections.append((block.text(), block.position()))
        block = block.next()
    return sections


class HelpWindow(QDialog):
    """左侧目录、右侧正文的使用帮助窗口。

    正文取自随包分发的 ``ui/assets/user-guide.md``，内容与 ``docs/user-guide.md`` 一致。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("使用帮助")
        self.setWindowIcon(app_icon())
        self.resize(880, 620)
        self.setMinimumSize(640, 420)
        self._sections: list[tuple[str, int]] = []

        self.toc = QListWidget()
        self.toc.setMinimumWidth(150)
        self.toc.setToolTip("章节目录")
        self.content = QTextBrowser()
        self.content.setOpenExternalLinks(False)
        self.content.setToolTip("使用手册正文")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.toc)
        splitter.addWidget(self.content)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([200, 660])

        close_button = QPushButton("关闭")
        close_button.setAutoDefault(False)
        close_button.clicked.connect(self.close)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter, 1)
        layout.addLayout(footer)

        self.toc.currentRowChanged.connect(self._jump_to_section)
        self.set_help_text(self._load_help_text())

    def set_help_text(self, markdown: str) -> None:
        """渲染 Markdown 正文，并按二级标题重建目录。"""
        self.content.setMarkdown(markdown)
        self._sections = _collect_sections(self.content.document())
        self.toc.blockSignals(True)
        self.toc.clear()
        for title, _position in self._sections:
            self.toc.addItem(title)
        self.toc.blockSignals(False)
        if self._sections:
            self.toc.setCurrentRow(0)

    @staticmethod
    def _load_help_text() -> str:
        """读取内置手册；资源缺失时退回简短提示而不是中断开窗。"""
        try:
            return (assets_dir() / _HELP_FILE_NAME).read_text(encoding="utf-8")
        except OSError:
            return _FALLBACK_TEXT

    def _jump_to_section(self, row: int) -> None:
        """把正文滚动到指定目录项对应的标题。"""
        if not 0 <= row < len(self._sections):
            return
        cursor: QTextCursor = self.content.textCursor()
        cursor.setPosition(self._sections[row][1])
        self.content.setTextCursor(cursor)
        self.content.ensureCursorVisible()
