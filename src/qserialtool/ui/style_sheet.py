"""浅色与深色主题的设计令牌和全局 QSS 样式表。

令牌是颜色的唯一来源：``apply_theme()`` 同时用它设置调色板和样式表，两者必须保持
一致，否则 palette 对比度测试将不再反映真实渲染结果。样式表刻意不声明任何字体属性，
数据区的等宽字体由 ``data_font()`` 在控件上单独设置。
"""

import sys
from dataclasses import dataclass
from pathlib import Path

from .style_qss import render_qss


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    """一套主题下的界面颜色令牌。"""

    window: str
    surface: str
    subtle: str
    editor: str
    input: str
    border: str
    border_strong: str
    text: str
    muted: str
    accent: str
    accent_fill: str
    accent_fill_hover: str
    accent_fill_pressed: str
    accent_soft: str


_TOKENS: dict[str, ThemeTokens] = {
    "light": ThemeTokens(
        window="#F3F4F6",
        surface="#FFFFFF",
        subtle="#F9FAFB",
        editor="#FFFFFF",
        input="#FFFFFF",
        border="#D8DCE3",
        border_strong="#C2C8D2",
        text="#1F2328",
        muted="#5B6472",
        accent="#2563EB",
        accent_fill="#2563EB",
        accent_fill_hover="#1D4ED8",
        accent_fill_pressed="#1E40AF",
        accent_soft="#EAF0FE",
    ),
    "dark": ThemeTokens(
        window="#1B1D21",
        surface="#232629",
        subtle="#2A2E33",
        editor="#17191C",
        input="#2A2E33",
        border="#34383E",
        border_strong="#454B54",
        text="#E6E8EB",
        muted="#9AA1AA",
        # 深色下强调色分两类：文字/边框用亮蓝保证对比度，实心按钮底用深蓝保证白字可读。
        accent="#6BA1FF",
        accent_fill="#2563EB",
        accent_fill_hover="#3B82F6",
        accent_fill_pressed="#1D4ED8",
        accent_soft="#1E2A3D",
    ),
}


def tokens(theme_name: str) -> ThemeTokens:
    """返回指定主题的颜色令牌。"""
    return _TOKENS[theme_name]


def assets_dir() -> Path:
    """返回样式资源目录；PyInstaller 单文件模式下指向解包目录。"""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "qserialtool" / "ui" / "assets"
    return Path(__file__).resolve().parent / "assets"


def build_stylesheet(theme_name: str) -> str:
    """按主题令牌生成全局 QSS。"""
    return render_qss(tokens(theme_name), assets_dir().as_posix())
