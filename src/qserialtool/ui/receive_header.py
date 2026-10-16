"""接收标题行的装配、折叠优先级与“⋯”溢出控制。"""

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QWidget,
)

from qserialtool.ui.theme_manager import CONTROL_HEIGHT_PX

# “接收”标题与格式下拉框之间的固定间隔，参与标题行溢出宽度估算。
HEADING_GAP = 12

# 标题行控件的折叠优先级：数值越大越先被收进“⋯”菜单；未列出的控件永不折叠。
FOLD_RANKS: tuple[tuple[str, int], ...] = (
    ("timestamp_check", 20),
    ("terminal_timestamp_check", 25),
    ("rx_check", 30),
    ("tx_check", 40),
    ("pause_button", 5),
    ("clear_button", 10),
    ("highlight_check", 45),
    ("wrap_check", 50),
    ("autoscroll_check", 60),
)


@dataclass(slots=True)
class HeaderItem:
    """标题行中一个参与宽度估算的控件。"""

    widget: QWidget
    rank: int
    mode_visible: bool = True


class HeaderOverflow(QObject):
    """按可用宽度把次要标题行控件折叠进“⋯”菜单。

    折叠只隐藏控件并在菜单里挂一个等价动作，不搬动控件本身，勾选状态和信号连接
    因此始终只有一处来源；宽度不足时优先折叠 ``rank`` 较大的控件。
    """

    def __init__(self, panel: QWidget, layout: QHBoxLayout) -> None:
        super().__init__(panel)
        self._panel = panel
        self._layout = layout
        self._items: list[HeaderItem] = []
        self._actions: dict[QWidget, QAction] = {}
        self._folded: set[QWidget] = set()
        self.button = QToolButton(panel)
        self.button.setText("⋯")
        self.button.setAutoRaise(True)
        self.button.setToolTip("更多显示选项")
        self.button.setFixedSize(CONTROL_HEIGHT_PX, CONTROL_HEIGHT_PX)
        self.button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu = QMenu(self.button)
        self.button.setMenu(self.menu)
        self.button.setVisible(False)

    def register(self, widget: QWidget, rank: int = 0) -> None:
        """登记标题行控件；``rank`` 大于 0 的控件可被折叠。"""
        self._items.append(HeaderItem(widget=widget, rank=rank))
        if rank <= 0:
            return
        action = self._build_action(widget)
        self._actions[widget] = action
        self.menu.addAction(action)
        action.setVisible(False)

    def set_mode_visible(self, widget: QWidget, visible: bool) -> None:
        """记录控件是否应随视图模式显示，然后重新评估折叠。"""
        item = self._item_for(widget)
        if item is None:
            widget.setVisible(visible)
            return
        item.mode_visible = visible
        self.reflow()

    def folded_widgets(self) -> tuple[QWidget, ...]:
        """按登记顺序返回当前被收进“⋯”菜单的控件。"""
        return tuple(item.widget for item in self._items if item.widget in self._folded)

    def reflow(self) -> None:
        """按当前面板宽度决定哪些控件需要折叠。"""
        available = self._available_width()
        if available <= 0:
            return
        candidates = [item for item in self._items if item.rank > 0 and item.mode_visible]
        candidates.sort(key=lambda item: item.rank, reverse=True)
        folded: set[QWidget] = set()
        while candidates and self._required_width(folded) > available:
            folded.add(candidates.pop(0).widget)
        self._apply(folded)

    def _available_width(self) -> int:
        margins = self._layout.contentsMargins()
        return self._panel.width() - margins.left() - margins.right()

    def _required_width(self, folded: set[QWidget]) -> int:
        width = HEADING_GAP
        shown = 0
        for item in self._items:
            if item.widget in folded or not item.mode_visible:
                continue
            width += item.widget.sizeHint().width()
            shown += 1
        spacing = self._layout.spacing()
        width += spacing * max(shown - 1, 0)
        if folded:
            width += spacing + self.button.sizeHint().width()
        return width

    def _apply(self, folded: set[QWidget]) -> None:
        self._folded = folded
        for widget, action in self._actions.items():
            item = self._item_for(widget)
            is_folded = widget in folded
            widget.setVisible(item.mode_visible and not is_folded)
            action.setVisible(is_folded)
        self.button.setVisible(bool(folded))

    def _item_for(self, widget: QWidget) -> HeaderItem | None:
        for item in self._items:
            if item.widget is widget:
                return item
        return None

    def _build_action(self, widget: QWidget) -> QAction:
        """为折叠控件生成等价菜单动作，并与原控件双向同步。"""
        action = QAction(widget.text(), self)
        action.setToolTip(widget.toolTip())
        if isinstance(widget, QAbstractButton) and widget.isCheckable():
            action.setCheckable(True)
            action.setChecked(widget.isChecked())
            action.toggled.connect(widget.setChecked)
            widget.toggled.connect(action.setChecked)
        else:
            action.triggered.connect(widget.click)
        return action


def assemble_header_row(
    layout: QHBoxLayout,
    *,
    heading: QLabel,
    filters: Sequence[QWidget],
    controls: Sequence[QWidget],
    overflow: HeaderOverflow,
) -> None:
    """按“标题—格式与过滤—操作”顺序装配标题行，并压到统一控件高度。

    ``filters`` 是以格式下拉框开头的左段控件，``controls`` 是贴右显示的操作段；
    折叠按钮固定在行尾最右侧，两段之间用 ``addStretch(1)`` 隔开。
    """
    layout.addWidget(heading)
    layout.addSpacing(HEADING_GAP)
    for widget in filters:
        layout.addWidget(widget)
    layout.addStretch(1)
    for widget in controls:
        layout.addWidget(widget)
    layout.addWidget(overflow.button)
    for widget in (*filters, *controls):
        widget.setFixedHeight(CONTROL_HEIGHT_PX)
