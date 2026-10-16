"""测试自定义标签栏：加号新建按钮跟随最后一个标签。"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QTabWidget, QWidget

from qserialtool.ui.style_sheet import build_stylesheet
from qserialtool.ui.tab_bar import SessionTabBar


def _build_tabs(qtbot: object, width: int = 480) -> tuple[QTabWidget, SessionTabBar]:
    """按主窗口的顺序装配标签栏：换栏后再开文档模式，标签栏才会占满整行。"""
    tabs = QTabWidget()
    bar = SessionTabBar(tabs)
    tabs.setTabBar(bar)
    tabs.setDocumentMode(True)
    qtbot.addWidget(tabs)
    tabs.resize(width, 240)
    tabs.show()
    qtbot.waitUntil(lambda: bar.width() == width, timeout=2000)
    return tabs, bar


def test_new_tab_button_follows_last_tab(qtbot: object) -> None:
    tabs, bar = _build_tabs(qtbot)
    button = bar.new_tab_button

    tabs.addTab(QWidget(), "会话 1")
    tabs.addTab(QWidget(), "会话 2")

    assert button.parentWidget() is bar
    assert button.isVisible()
    assert button.x() > bar.tabRect(1).right()

    previous = button.x()
    tabs.addTab(QWidget(), "会话 3")
    assert button.x() > bar.tabRect(2).right()
    assert button.x() > previous


def test_new_tab_button_moves_back_after_tab_removed(qtbot: object) -> None:
    tabs, bar = _build_tabs(qtbot)
    for title in ("会话 1", "会话 2", "会话 3"):
        tabs.addTab(QWidget(), title)
    button = bar.new_tab_button
    wide = button.x()

    tabs.removeTab(2)

    assert button.x() < wide
    assert button.x() > bar.tabRect(1).right()


def test_new_tab_button_stays_visible_without_tabs(qtbot: object) -> None:
    tabs, bar = _build_tabs(qtbot)
    button = bar.new_tab_button

    qtbot.waitUntil(button.isVisible, timeout=2000)

    assert tabs.count() == 0
    assert button.x() <= 8


def test_new_tab_button_hides_when_tabs_overflow(qtbot: object) -> None:
    tabs, bar = _build_tabs(qtbot, width=360)
    button = bar.new_tab_button

    for index in range(8):
        tabs.addTab(QWidget(), f"会话 {index + 1} 的较长标题")
    assert not button.isVisible()

    while tabs.count() > 1:
        tabs.removeTab(0)
    assert not bar._has_tabs_overflow()
    assert button.isVisible()


def test_new_tab_button_click_emits_new_tab_requested(qtbot: object) -> None:
    _, bar = _build_tabs(qtbot)
    requested: list[bool] = []
    bar.new_tab_requested.connect(lambda: requested.append(True))
    button = bar.new_tab_button
    qtbot.waitUntil(button.isVisible, timeout=2000)

    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    assert requested == [True]


def test_new_tab_button_uses_prominent_accent_style(qtbot: object) -> None:
    _, bar = _build_tabs(qtbot)
    button = bar.new_tab_button

    assert button.objectName() == "newTabButton"
    assert button.size() == QSize(28, 28)
    assert button.iconSize() == QSize(16, 16)
    assert not button.icon().isNull()
    assert "#newTabButton" in build_stylesheet("light")
