"""发送编辑器和发送操作面板。"""

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qserialtool.application import SessionController
from qserialtool.domain import (
    DomainError,
    LineEnding,
    SessionState,
    append_line_ending,
    encode_text,
    parse_hex,
)

_NEWLINES: tuple[tuple[str, LineEnding], ...] = (
    ("无换行", "none"),
    ("CR", "cr"),
    ("LF", "lf"),
    ("CRLF", "crlf"),
)


class SendPanel(QWidget):
    """编辑并发送文本或 HEX 数据。"""

    def __init__(self, *, controller: SessionController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._build_ui()
        self.set_connected(controller.state is SessionState.CONNECTED)

    def _build_ui(self) -> None:
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("发送格式"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("文本", "text")
        self.mode_combo.addItem("HEX", "hex")
        toolbar.addWidget(self.mode_combo)
        toolbar.addWidget(QLabel("换行"))
        self.newline_combo = QComboBox()
        for label, value in _NEWLINES:
            self.newline_combo.addItem(label, value)
        toolbar.addWidget(self.newline_combo)
        toolbar.addStretch(1)
        self.send_button = QPushButton("发送")
        self.send_button.setToolTip("Ctrl+Enter")
        self.send_button.clicked.connect(self.send)
        toolbar.addWidget(self.send_button)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("输入待发送内容，按 Ctrl+Enter 发送")
        self.editor.setMinimumHeight(80)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toolbar)
        layout.addWidget(self.editor)

        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.editor)
        shortcut.activated.connect(self.send)

    def set_connected(self, connected: bool) -> None:
        """根据连接状态启用或禁用发送按钮。"""
        self.send_button.setEnabled(connected)

    def send(self) -> None:
        """解析当前输入并调用会话控制器。"""
        try:
            raw = self._build_payload()
            self._controller.send(raw)
        except DomainError as exc:
            QMessageBox.warning(self, "发送失败", exc.message)

    def _build_payload(self) -> bytes:
        content = self.editor.toPlainText()
        mode = self.mode_combo.currentData()
        if mode == "hex":
            data = parse_hex(content)
        else:
            data = encode_text(content, self._controller.config.encoding)
        return append_line_ending(data, self.newline_combo.currentData())
