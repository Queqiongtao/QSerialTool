"""应用浅色、深色和跟随系统主题。"""

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from qserialtool.domain import Theme

from .style_sheet import ThemeTokens, build_stylesheet, tokens

_DISABLED_TEXT_ROLES = (
    QPalette.ColorRole.WindowText,
    QPalette.ColorRole.Text,
    QPalette.ColorRole.ButtonText,
)


def _palette_roles(colors: ThemeTokens) -> tuple[tuple[QPalette.ColorRole, str], ...]:
    """把主题令牌映射为调色板角色，样式表中的同名颜色必须与之一致。"""
    return (
        (QPalette.ColorRole.Window, colors.window),
        (QPalette.ColorRole.WindowText, colors.text),
        (QPalette.ColorRole.Base, colors.editor),
        (QPalette.ColorRole.AlternateBase, colors.subtle),
        (QPalette.ColorRole.Text, colors.text),
        (QPalette.ColorRole.Button, colors.surface),
        (QPalette.ColorRole.ButtonText, colors.text),
        (QPalette.ColorRole.Highlight, colors.accent_fill),
        (QPalette.ColorRole.HighlightedText, "#FFFFFF"),
        (QPalette.ColorRole.ToolTipBase, colors.surface),
        (QPalette.ColorRole.ToolTipText, colors.text),
    )


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


@dataclass(frozen=True, slots=True)
class HighlightColors:
    """终端模式高亮使用的颜色。"""

    address: str
    link: str
    success: str
    error: str
    warning: str


_HIGHLIGHT_COLORS: dict[str, HighlightColors] = {
    "light": HighlightColors(
        address="#8b2f8f",
        link="#0e7490",
        success="#14713d",
        error="#b3261e",
        warning="#8a5a00",
    ),
    "dark": HighlightColors(
        address="#d9a2f5",
        link="#6fd7e6",
        success="#5cc98c",
        error="#ff8a80",
        warning="#ffc14d",
    ),
}

# ANSI 16 色语义索引，终端模型只存索引，渲染时再映射到当前主题。
_ANSI_COLORS: dict[str, tuple[str, ...]] = {
    "light": (
        "#000000",
        "#b3261e",
        "#14713d",
        "#8a5a00",
        "#1f5fa8",
        "#8b2f8f",
        "#0e7490",
        "#4b5563",
        "#6b7280",
        "#e5484d",
        "#2e9e5b",
        "#b7791f",
        "#3b82f6",
        "#b05fd0",
        "#0ea5b7",
        "#111827",
    ),
    "dark": (
        "#3f4650",
        "#ff8a80",
        "#5cc98c",
        "#ffc14d",
        "#6fb3f2",
        "#d9a2f5",
        "#6fd7e6",
        "#c9cfd6",
        "#8f959c",
        "#ff6b61",
        "#7ee0a8",
        "#ffd36b",
        "#93c7f8",
        "#e6b8ff",
        "#8fe6f2",
        "#ffffff",
    ),
}

# xterm 256 色：16-231 为 6×6×6 色立方，232-255 为 24 级灰度。
_XTERM_CUBE_LEVELS = (0, 95, 135, 175, 215, 255)
_XTERM_CUBE_START = 16
_XTERM_CUBE_SIZE = 216
_XTERM_GRAY_START = 232
_XTERM_GRAY_LAST = 255
_XTERM_GRAY_BASE = 8
_XTERM_GRAY_STEP = 10


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


def ansi_colors() -> tuple[str, ...]:
    """返回当前主题下的 ANSI 16 色，索引与 SGR 语义一致。"""
    return _ANSI_COLORS[_ThemeState.resolved]


def highlight_colors() -> HighlightColors:
    """返回当前主题下的终端模式高亮颜色。"""
    return _HIGHLIGHT_COLORS[_ThemeState.resolved]


def ansi_color(index: int) -> str:
    """把 ANSI 颜色索引（0-255）映射为当前主题下的十六进制颜色。"""
    palette = ansi_colors()
    if 0 <= index < len(palette):
        return palette[index]
    if _XTERM_CUBE_START <= index < _XTERM_CUBE_START + _XTERM_CUBE_SIZE:
        offset = index - _XTERM_CUBE_START
        red = _XTERM_CUBE_LEVELS[offset // 36]
        green = _XTERM_CUBE_LEVELS[(offset // 6) % 6]
        blue = _XTERM_CUBE_LEVELS[offset % 6]
        return f"#{red:02x}{green:02x}{blue:02x}"
    if _XTERM_GRAY_START <= index <= _XTERM_GRAY_LAST:
        level = _XTERM_GRAY_BASE + _XTERM_GRAY_STEP * (index - _XTERM_GRAY_START)
        return f"#{level:02x}{level:02x}{level:02x}"
    raise ValueError(f"ANSI 颜色索引超出范围：{index}")


DATA_FONT_PRESETS: tuple[int, ...] = (9, 10, 11, 12, 14, 16, 18, 20, 24)

# 标题行与顶栏控件统一高度，避免下拉框、按钮和勾选框基线不齐。
CONTROL_HEIGHT_PX = 24


def data_font(size: int = 0) -> QFont:
    """返回接收与发送数据区使用的等宽字体；size 为 0 时沿用系统默认字号。"""
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setFixedPitch(True)
    if size > 0:
        font.setPointSize(size)
    return font


def apply_theme(app: QApplication, theme: Theme) -> None:
    """为应用设置统一调色板与全局样式表。"""
    resolved = resolve_theme(theme)
    _ThemeState.resolved = resolved
    app.setStyle("Fusion")
    colors = tokens(resolved)
    palette = app.style().standardPalette()
    for role, value in _palette_roles(colors):
        palette.setColor(role, QColor(value))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors.muted))
    # 浅色沿用平台自带的禁用态配色；深色必须显式指定，否则禁用控件与可用控件同样醒目。
    if resolved == "dark":
        for role in _DISABLED_TEXT_ROLES:
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors.muted))
    app.setPalette(palette)
    app.setStyleSheet(build_stylesheet(resolved))
