"""应用浅色、深色和跟随系统主题。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from qserialtool.domain import Theme


def resolve_theme(theme: Theme) -> str:
    """把系统主题解析成明确的 light 或 dark。"""
    if theme != "system":
        return theme
    app = QApplication.instance()
    if app is None:
        return "light"
    if hasattr(app, "styleHints") and app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
        return "dark"
    return "light"


def apply_theme(app: QApplication, theme: Theme) -> None:
    """为应用设置统一调色板。"""
    resolved = resolve_theme(theme)
    app.setStyle("Fusion")
    if resolved == "dark":
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#202225"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#e6e6e6"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#17191c"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#292c30"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#e6e6e6"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#2e3135"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e6e6e6"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#2f6fa8"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        app.setPalette(palette)
    else:
        app.setPalette(app.style().standardPalette())
