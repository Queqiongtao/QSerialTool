"""标签栏：把“+”新建按钮放在最后一个标签右侧，类似 Windows Terminal。"""

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QIcon, QResizeEvent, QShowEvent
from PySide6.QtWidgets import QTabBar, QToolButton, QWidget

from qserialtool.ui.style_sheet import assets_dir
from qserialtool.ui.theme_manager import HEADER_BUTTON_SIZE_PX

# “+”与最后一个标签之间的水平间距（像素）。
_BUTTON_GAP_PX = 4
# 标签栏为空时“+”距左边缘的水平余量（像素）。
_EMPTY_MARGIN_PX = 2
# “+”按钮内矢量图标的边长（像素）。
_BUTTON_ICON_PX = 16


class SessionTabBar(QTabBar):
    """最后一个标签右侧紧跟“+”新建按钮的标签栏。

    按钮是标签栏的子控件：标签增删、改名、拖动排序和标签栏尺寸变化后
    都会重新贴到最后一个标签右侧；标签总宽超出标签栏（QTabBar 启用内部
    滚动按钮）或按钮放不下时暂时隐藏，``Ctrl+T`` 与“☰”菜单仍可新建会话。
    """

    new_tab_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.new_tab_button = QToolButton(self)
        # objectName 供 style_qss.py 的实心强调色规则选中；白色图标位于
        # 两侧主题同值的 accent_fill 底上，不再受样式表重刷字体的影响。
        self.new_tab_button.setObjectName("newTabButton")
        self.new_tab_button.setIcon(QIcon(str(assets_dir() / "plus.svg")))
        self.new_tab_button.setIconSize(QSize(_BUTTON_ICON_PX, _BUTTON_ICON_PX))
        self.new_tab_button.setFixedSize(HEADER_BUTTON_SIZE_PX, HEADER_BUTTON_SIZE_PX)
        self.new_tab_button.setAutoRaise(True)
        self.new_tab_button.setToolTip("新建会话 (Ctrl+T)")
        self.new_tab_button.clicked.connect(self._on_new_tab_clicked)
        self._reposition_new_tab_button()

    def tabLayoutChange(self) -> None:
        """标签增删、改标题或拖动后重新摆放“+”按钮。"""
        super().tabLayoutChange()
        self._reposition_new_tab_button()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._reposition_new_tab_button()

    def showEvent(self, event: QShowEvent) -> None:
        # 窗口从小化或隐藏恢复时尺寸可能没有变化，resizeEvent 不会触发。
        super().showEvent(event)
        self._reposition_new_tab_button()

    def _on_new_tab_clicked(self, _checked: bool = False) -> None:
        """吞掉 clicked 的勾选参数后转发为无参的 new_tab_requested。"""
        self.new_tab_requested.emit()

    def _reposition_new_tab_button(self) -> None:
        button = self.new_tab_button
        if self.count() > 0:
            last = self.tabRect(self.count() - 1)
            x = last.right() + 1 + _BUTTON_GAP_PX
            y = last.top() + max(0, (last.height() - button.height()) // 2)
        else:
            x = _EMPTY_MARGIN_PX
            y = max(0, (self.height() - button.height()) // 2)
        button.setVisible(not self._has_tabs_overflow() and x + button.width() <= self.width())
        button.move(x, y)

    def _has_tabs_overflow(self) -> bool:
        """标签总宽超过标签栏时 QTabBar 显示内部滚动按钮，“+”此时必须隐藏。"""
        total = sum(self.tabRect(index).width() for index in range(self.count()))
        return total > self.width()
