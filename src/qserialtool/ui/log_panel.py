"""自动日志和手动导出面板。"""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from qserialtool.application import SessionController, default_log_directory
from qserialtool.domain import DomainError, LogFormat, SessionSnapshot, SessionState


class LogPanel(QGroupBox):
    """配置自动日志、打开日志目录并导出内存缓冲。"""

    preferences_changed = Signal()

    def __init__(
        self,
        *,
        controller: SessionController,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("日志与导出", parent)
        self._controller = controller
        self._loading = False
        self._build_ui()
        self._connect_changes()
        self.apply_preferences(
            enabled=controller.auto_log_enabled,
            log_format=controller.auto_log_format,
            directory=controller.auto_log_directory,
        )
        self.apply_snapshot(controller.snapshot)

    def _build_ui(self) -> None:
        self.enabled_check = QCheckBox("自动保存")
        self.format_combo = QComboBox()
        self.format_combo.addItem("CSV", "csv")
        self.format_combo.addItem("TXT", "txt")
        self.directory_edit = QLineEdit()
        self.browse_button = QPushButton("选择目录")
        self.open_button = QPushButton("打开目录")
        self.export_button = QPushButton("导出当前缓冲")
        self.status_label = QLabel()
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._status_text = ""

        layout = QGridLayout(self)
        layout.addWidget(self.enabled_check, 0, 0)
        layout.addWidget(QLabel("格式"), 0, 1)
        layout.addWidget(self.format_combo, 0, 2)
        layout.addWidget(QLabel("目录"), 1, 0)
        # 路径独占一行避免被按钮挤到截断；选择/打开等分一行，导出作为主操作独占一行。
        layout.addWidget(self.directory_edit, 1, 1, 1, 2)
        button_row = QHBoxLayout()
        button_row.setSpacing(6)
        buttons = (self.browse_button, self.open_button)
        width = max(button.sizeHint().width() for button in buttons)
        for button in buttons:
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setMinimumWidth(width)
            button_row.addWidget(button, 1)
        layout.addLayout(button_row, 2, 0, 1, 3)
        layout.addWidget(self.export_button, 3, 0, 1, 3)
        layout.addWidget(self.status_label, 4, 0, 1, 3)

    def _connect_changes(self) -> None:
        self.enabled_check.toggled.connect(self._settings_changed)
        self.format_combo.currentIndexChanged.connect(self._settings_changed)
        self.directory_edit.textEdited.connect(self._settings_changed)
        self.browse_button.clicked.connect(self._browse)
        self.open_button.clicked.connect(self._open_directory)
        self.export_button.clicked.connect(self._export)

    def apply_preferences(
        self,
        *,
        enabled: bool,
        log_format: LogFormat,
        directory: str,
    ) -> None:
        """把持久化偏好加载到控件。"""
        self._loading = True
        try:
            self.enabled_check.setChecked(enabled)
            index = self.format_combo.findData(log_format)
            self.format_combo.setCurrentIndex(index if index >= 0 else 0)
            self.directory_edit.setText(directory or str(default_log_directory()))
            self.directory_edit.setCursorPosition(0)
        finally:
            self._loading = False

    def apply_snapshot(self, snapshot: SessionSnapshot) -> None:
        """根据连接状态启用或禁用日志设置。"""
        editable = snapshot.state in {SessionState.DISCONNECTED, SessionState.ERROR}
        self.enabled_check.setEnabled(editable)
        self.format_combo.setEnabled(editable)
        self.directory_edit.setEnabled(editable)
        self.browse_button.setEnabled(editable)
        if self._controller.log_path is not None:
            self._set_status(f"日志：{self._controller.log_path}")
        else:
            self._set_status("")

    def _set_status(self, text: str) -> None:
        """设置状态文本，始终保留完整提示并按宽度做中间省略。"""
        self._status_text = text
        self.status_label.setToolTip(text)
        self._apply_status_elide()

    def _apply_status_elide(self) -> None:
        width = self.status_label.width()
        if width <= 0:
            elided = self._status_text
        else:
            elided = self.status_label.fontMetrics().elidedText(
                self._status_text,
                Qt.TextElideMode.ElideMiddle,
                width,
            )
        if elided != self.status_label.text():
            self.status_label.setText(elided)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_status_elide()

    def preferences(self) -> tuple[bool, LogFormat, str]:
        """返回当前自动日志偏好。"""
        return (
            self.enabled_check.isChecked(),
            self.format_combo.currentData(),  # type: ignore[return-value]
            self.directory_edit.text().strip(),
        )

    def _settings_changed(self) -> None:
        if self._loading:
            return
        enabled, log_format, directory = self.preferences()
        try:
            self._controller.update_log_preferences(
                enabled=enabled,
                log_format=log_format,
                directory=directory,
            )
        except DomainError as exc:
            QMessageBox.warning(self, "日志设置失败", exc.message)
            return
        self.preferences_changed.emit()

    def _browse(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "选择日志目录",
            self.directory_edit.text(),
        )
        if selected:
            self.directory_edit.setText(selected)
            self.directory_edit.setCursorPosition(0)
            self._settings_changed()

    def _open_directory(self) -> None:
        directory = Path(self.directory_edit.text().strip() or str(default_log_directory()))
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "打开目录失败", str(exc))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def _export(self) -> None:
        log_format: LogFormat = self.format_combo.currentData()
        extension = "csv" if log_format == "csv" else "txt"
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "导出当前缓冲",
            str(Path(self.directory_edit.text()).with_suffix(f".{extension}")),
            f"{extension.upper()} 文件 (*.{extension})",
        )
        if selected:
            self.export_to(Path(selected), log_format)

    def export_to(self, path: Path, log_format: LogFormat) -> None:
        """导出到明确路径，便于测试与后续自动化。"""
        try:
            count = self._controller.export_records(path, log_format)
        except DomainError as exc:
            QMessageBox.warning(self, "导出失败", exc.message)
            return
        self._set_status(f"已导出 {count} 条：{path}")
