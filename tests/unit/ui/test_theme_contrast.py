"""校验浅色与深色主题的对比度与禁用态可辨识度。"""

from collections.abc import Iterator

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from qserialtool.ui import apply_theme, data_colors, resolved_theme

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
