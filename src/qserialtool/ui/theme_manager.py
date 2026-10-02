"""应用浅色、深色和跟随系统主题。"""

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from qserialtool.domain import Theme

_DARK_ROLES: tuple[tuple[QPalette.ColorRole, str], ...] = (
    (QPalette.ColorRole.Window, "#202225"),
    (QPalette.ColorRole.WindowText, "#e6e6e6"),
    (QPalette.ColorRole.Base, "#17191c"),
    (QPalette.ColorRole.AlternateBase, "#292c30"),
    (QPalette.ColorRole.Text, "#e6e6e6"),
    (QPalette.ColorRole.Button, "#2e3135"),
    (QPalette.ColorRole.ButtonText, "#e6e6e6"),
    (QPalette.ColorRole.Highlight, "#2f6fa8"),
    (QPalette.ColorRole.HighlightedText, "#ffffff"),
)

_DISABLED_TEXT_ROLES = (
    QPalette.ColorRole.WindowText,
    QPalette.ColorRole.Text,
    QPalette.ColorRole.ButtonText,
)

_PLACEHOLDER_COLORS = {"light": "#666666", "dark": "#8f959c"}

# 浅色主题沿用平台自带的禁用态配色，深色主题必须显式指定，否则禁用控件与可用控件同样醒目。
_DISABLED_TEXT_COLORS: dict[str, str | None] = {"light": None, "dark": "#8f959c"}


@dataclass(frozen=True, slots=True)
class DataColors:
    """当前主题下数据区与状态指示使用的颜色。"""

    rx: str
    tx: str
    system: str
    connected: str
    error: str
    pending: str
    idle: str


_THEME_COLORS: dict[str, DataColors] = {
    "light": DataColors(
        rx="#14713d",
        tx="#1f5fa8",
        system="#666666",
        connected="#14713d",
        error="#b3261e",
        pending="#8a5a00",
        idle="#666666",
    ),
    "dark": DataColors(
        rx="#5cc98c",
        tx="#6fb3f2",
        system="#a3a9b0",
        connected="#5cc98c",
        error="#ff8a80",
        pending="#ffc14d",
        idle="#8f959c",
    ),
}


class _ThemeState:
    """记录最近一次解析出的主题，供数据区取色使用。"""

    resolved = "light"


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


def resolved_theme() -> str:
    """返回最近一次应用主题时解析出的明确主题。"""
    return _ThemeState.resolved


def data_colors() -> DataColors:
    """返回当前主题的数据区与状态指示颜色。"""
    return _THEME_COLORS[_ThemeState.resolved]


def data_font() -> QFont:
    """返回接收与发送数据区使用的等宽字体。"""
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setFixedPitch(True)
    return font


def apply_theme(app: QApplication, theme: Theme) -> None:
    """为应用设置统一调色板。"""
    resolved = resolve_theme(theme)
    _ThemeState.resolved = resolved
    app.setStyle("Fusion")
    palette = app.style().standardPalette()
    if resolved == "dark":
        for role, value in _DARK_ROLES:
            palette.setColor(role, QColor(value))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(_PLACEHOLDER_COLORS[resolved]))
    disabled_text = _DISABLED_TEXT_COLORS[resolved]
    if disabled_text is not None:
        for role in _DISABLED_TEXT_ROLES:
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(disabled_text))
    app.setPalette(palette)
