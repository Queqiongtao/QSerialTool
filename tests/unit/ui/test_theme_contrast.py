"""校验浅色与深色主题的对比度与禁用态可辨识度。"""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from qserialtool.ui import apply_theme, data_colors, resolved_theme
from qserialtool.ui.style_sheet import assets_dir, build_stylesheet, tokens
from qserialtool.ui.theme_manager import ansi_color, highlight_colors

_DATA_COLOR_FIELDS = ("rx", "tx", "system", "connected", "error", "pending", "idle")


def _channel(value: int) -> float:
    ratio = value / 255
    if ratio <= 0.03928:
        return ratio / 12.92
    return ((ratio + 0.055) / 1.055) ** 2.4


def _luminance(color: str) -> float:
    digits = color.lstrip("#")
    red, green, blue = (int(digits[index : index + 2], 16) for index in (0, 2, 4))
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def _contrast(foreground: str, background: str) -> float:
    lighter, darker = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.fixture
def app(qapp: QApplication) -> Iterator[QApplication]:
    """返回应用实例，并在用例结束后恢复浅色主题。"""
    yield qapp
    apply_theme(qapp, "light")


def _base_color(app: QApplication) -> str:
    return app.palette().color(QPalette.ColorRole.Base).name()


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_data_colors_meet_contrast_targets(app: QApplication, theme_name: str) -> None:
    apply_theme(app, theme_name)
    assert resolved_theme() == theme_name
    background = _base_color(app)
    colors = data_colors()
    for field in _DATA_COLOR_FIELDS:
        value = getattr(colors, field)
        assert _contrast(value, background) >= 4.5, f"{theme_name} {field}={value}"


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_placeholder_text_meets_contrast_targets(app: QApplication, theme_name: str) -> None:
    apply_theme(app, theme_name)
    placeholder = app.palette().color(QPalette.ColorRole.PlaceholderText).name()
    assert _contrast(placeholder, _base_color(app)) >= 4.5


def test_dark_disabled_text_is_dimmer_than_enabled(app: QApplication) -> None:
    apply_theme(app, "dark")
    palette = app.palette()
    enabled = palette.color(QPalette.ColorRole.WindowText).name()
    disabled = palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText).name()
    assert disabled != enabled
    assert _luminance(disabled) < _luminance(enabled)


@pytest.mark.parametrize(
    "index, expected",
    [
        (16, "#000000"),
        (196, "#ff0000"),
        (231, "#ffffff"),
        (232, "#080808"),
        (255, "#eeeeee"),
    ],
)
def test_ansi_color_maps_256_palette(index: int, expected: str) -> None:
    assert ansi_color(index) == expected


@pytest.mark.parametrize(
    "theme_name, expected",
    [("light", "#111827"), ("dark", "#ffffff")],
)
def test_ansi_color_uses_theme_for_low_indices(
    app: QApplication, theme_name: str, expected: str
) -> None:
    apply_theme(app, theme_name)
    assert ansi_color(15) == expected


def test_ansi_color_rejects_out_of_range_index() -> None:
    with pytest.raises(ValueError):
        ansi_color(256)


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_highlight_colors_meet_contrast_targets(app: QApplication, theme_name: str) -> None:
    apply_theme(app, theme_name)
    background = _base_color(app)
    colors = highlight_colors()
    for field in ("address", "link", "success", "error", "warning"):
        value = getattr(colors, field)
        assert _contrast(value, background) >= 4.5, f"{theme_name} {field}={value}"


def _data_area_font_declarations(stylesheet: str) -> list[str]:
    """返回样式表中作用在数据区控件上的字体声明，正常应为空。"""
    blocks = re.findall(r"([^{}]+)\{([^{}]*)\}", stylesheet)
    offenders: list[str] = []
    for selector, body in blocks:
        if "QPlainTextEdit" not in selector and "QTextEdit" not in selector:
            continue
        offenders.extend(line.strip() for line in body.splitlines() if "font" in line.lower())
    return offenders


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_apply_theme_installs_stylesheet(app: QApplication, theme_name: str) -> None:
    apply_theme(app, theme_name)
    assert app.styleSheet()
    assert app.styleSheet() == build_stylesheet(theme_name)


def test_light_and_dark_stylesheets_differ(app: QApplication) -> None:
    apply_theme(app, "light")
    light = app.styleSheet()
    apply_theme(app, "dark")
    assert app.styleSheet() != light


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_stylesheet_colors_come_from_tokens(app: QApplication, theme_name: str) -> None:
    colors = tokens(theme_name)
    stylesheet = build_stylesheet(theme_name)
    for value in (
        colors.window,
        colors.surface,
        colors.editor,
        colors.border,
        colors.text,
        colors.muted,
        colors.accent,
        colors.accent_fill,
    ):
        assert value in stylesheet


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_token_text_colors_meet_contrast_targets(theme_name: str) -> None:
    colors = tokens(theme_name)
    for surface in (colors.surface, colors.editor, colors.input):
        for field in ("text", "muted", "accent"):
            value = getattr(colors, field)
            assert _contrast(value, surface) >= 4.5, f"{theme_name} {field} on {surface}"
    assert _contrast("#FFFFFF", colors.accent_fill) >= 4.5


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_stylesheet_does_not_override_data_font(theme_name: str) -> None:
    stylesheet = build_stylesheet(theme_name)
    assert "QPlainTextEdit" in stylesheet
    assert _data_area_font_declarations(stylesheet) == []
    assert "font-family" not in stylesheet.lower()
    assert "font-size" not in stylesheet.lower()


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_stylesheet_asset_urls_exist(theme_name: str) -> None:
    stylesheet = build_stylesheet(theme_name)
    urls = re.findall(r'url\("([^"]+)"\)', stylesheet)
    assert urls
    for url in urls:
        assert Path(url).is_file(), url
        assert Path(url).is_relative_to(assets_dir())
