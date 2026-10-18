"""Windows Terminal 风格的标题行：标签行兼作窗口标题栏。

Windows 下去掉系统标题栏（``WS_CAPTION``）但保留可缩放边框（``WS_THICKFRAME``），
因此拖动、边缘缩放、Aero Snap、双击最大化/还原、右键系统菜单与 DWM 阴影都保持
系统行为；本模块只做四处最小原生处理：

- ``WM_NCCALCSIZE``：最大化时把客户区固定为显示器工作区，避免露出边框缝隙或
  被任务栏遮挡（普通状态交给默认处理，客户区即窗口矩形去掉原生边框）。
- ``WM_NCHITTEST``：标签行空白处返回 ``HTCAPTION``，变成可拖动区域；标签本身、
  “+”新建按钮、滚动按钮及其他控件交回默认处理，点击仍然正常。
- DWM 窗口属性：声明 Win11 圆角并把窗口边框描边改为主题的窗口底色，消除系统
  默认描边在深色主题下呈浅色细线的观感；沉浸式深色属性以 ``apply_theme()`` 向
  Qt 声明的配色方案为主（平台插件负责维护），这里只直写一份作为兜底。
- ``keep_window_hidden()``：构造期间对尚未显示的原生窗口执行 ``ShowWindow
  (SW_HIDE)``，抵消部分启动路径下系统把主窗口按默认尺寸提前显示约一秒的
  问题，第一个可见帧由应用自己的 ``show()`` 决定。

原生钩子只在 Windows 桌面平台生效；Linux 的 ``xcb``/``wayland`` 会话改用
``FramelessWindowHint`` 去装饰并自行处理拖动、双击最大化、边缘缩放与右键
窗口菜单，达到与 Windows 相同的单行标题行；离屏平台走普通窗口路径，
测试环境仍能看到控件树。
"""

from __future__ import annotations

import ctypes
import sys
from functools import lru_cache

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt
from PySide6.QtGui import QContextMenuEvent, QCursor, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMenu,
    QTabBar,
    QToolButton,
    QWidget,
)

from qserialtool.ui.icons import svg_icon
from qserialtool.ui.style_sheet import tokens
from qserialtool.ui.theme_manager import HEADER_BUTTON_SIZE_PX

# 窗口按钮宽度与图标边长（像素）；高度与标签栏“+”“☰”一致。
WINDOW_BUTTON_WIDTH_PX = 40
_BUTTON_ICON_PX = 16

# ShowWindow 的隐藏命令：构造期间用它在原生层强制保持窗口不可见。
_SW_HIDE = 0

_WINDOWS = sys.platform.startswith("win")

_GWL_STYLE = -16
_WS_CAPTION = 0x00C00000
_SWP_NOMOVE = 0x0002
_SWP_NOSIZE = 0x0001
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020

_WM_NCCALCSIZE = 0x0083
_WM_NCHITTEST = 0x0084
_HTCAPTION = 2
_MONITOR_DEFAULTTONEAREST = 2

# DWM 主题化窗口属性：深色沉浸式边框（Win10 1903 前后属性 id 不同）、Win11 圆角
# 与边框描边颜色（Win11 22000+；系统默认描边偏浅，深色主题下呈浅色细线）。
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2
_DWMWA_BORDER_COLOR = 34

_GENERIC_MSG = b"windows_generic_MSG"


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint),
        ("pt", _POINT),
    ]


class _NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", _RECT * 3), ("lppos", ctypes.c_void_p)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_uint),
    ]


class _Api:
    """user32 方法与 64 位安全的参数签名缓存。"""

    def __init__(self) -> None:
        user32 = ctypes.windll.user32
        self.user32 = user32
        self.get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        self.set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        self.get_long.restype = ctypes.c_ssize_t
        self.get_long.argtypes = (ctypes.c_void_p, ctypes.c_int)
        self.set_long.restype = ctypes.c_ssize_t
        self.set_long.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t)
        user32.SetWindowPos.argtypes = (
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        )
        user32.IsZoomed.argtypes = (ctypes.c_void_p,)
        user32.ShowWindow.argtypes = (ctypes.c_void_p, ctypes.c_int)
        user32.ShowWindow.restype = ctypes.c_int
        user32.MonitorFromWindow.restype = ctypes.c_void_p
        user32.MonitorFromWindow.argtypes = (ctypes.c_void_p, ctypes.c_uint)
        user32.GetMonitorInfoW.argtypes = (ctypes.c_void_p, ctypes.POINTER(_MONITORINFO))
        user32.ScreenToClient.argtypes = (ctypes.c_void_p, ctypes.POINTER(_POINT))
        dwmapi = ctypes.windll.dwmapi
        self.dwm_set_window_attribute = dwmapi.DwmSetWindowAttribute
        self.dwm_set_window_attribute.restype = ctypes.HRESULT
        self.dwm_set_window_attribute.argtypes = (
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_uint,
        )


@lru_cache(maxsize=1)
def _api() -> _Api:
    """懒加载 user32 封装，避免在非 Windows 平台导入时触碰 WinAPI。"""
    return _Api()


def is_windows() -> bool:
    """是否运行在 Windows（决定是否使用 WinAPI 原生钩子）。"""
    return _WINDOWS


def _platform_name() -> str:
    """返回 Qt 平台插件名；没有 QApplication 时返回空字符串。"""
    app = QApplication.instance()
    return app.platformName() if app is not None else ""


def uses_native_chrome() -> bool:
    """是否启用 Windows 原生自定义标题栏钩子。

    离屏平台没有真实窗口消息，跳过原生处理，测试仍能检查完整控件树。
    """
    if not _WINDOWS:
        return False
    return _platform_name() != "offscreen"


def uses_custom_title_bar() -> bool:
    """是否使用应用自绘标题行（标签行兼作标题栏并装配窗口按钮）。

    Windows 桌面与 Linux 的 ``xcb``/``wayland`` 会话启用；离屏平台不启用，
    测试仍走普通窗口路径并检查完整控件树。
    """
    platform = _platform_name()
    if platform == "offscreen":
        return False
    if _WINDOWS:
        return True
    return sys.platform.startswith("linux") and platform in {"xcb", "wayland"}


def keep_window_hidden(window: QWidget) -> None:
    """对尚未显示的原生窗口执行一次隐藏，保证构造期间窗口不可见。

    实测部分 Windows 启动路径上，主窗口会在构造中途（去掉系统标题栏与恢复
    几何之前）以默认尺寸加系统标题栏的状态被提前显示约一秒，随后才跳变到
    保存状态，观感是“先小窗口、再放大”。在构造关键点与显示前调用本函数，
    把第一个可见帧留给应用自己的 ``show()``；窗口已被应用显示后不再触碰，
    离屏与非 Windows 平台直接返回，不产生任何句柄操作。
    """
    if not uses_native_chrome() or window.isVisible():
        return
    hwnd = int(window.winId())
    if hwnd == 0:
        return
    _api().user32.ShowWindow(hwnd, _SW_HIDE)


class WindowButtons(QWidget):
    """标题行右侧的最小化、最大化（还原）与关闭按钮。"""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._window = window
        self.setObjectName("windowControls")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.minimize_button = self._build_button("windowMinButton", "最小化")
        self.minimize_button.setIcon(svg_icon("window-minimize"))
        self.maximize_button = self._build_button("windowMaxButton", "最大化")
        self.close_button = self._build_button("windowCloseButton", "关闭")
        # 关闭按钮的图标与悬停反白由 style_qss.py 的 image 规则切换（与标签关闭
        # 按钮一致），这里不 setIcon，避免图标与样式表绘制相互覆盖。
        self.minimize_button.clicked.connect(window.showMinimized)
        self.maximize_button.clicked.connect(self.toggle_maximized)
        self.close_button.clicked.connect(window.close)
        window.installEventFilter(self)
        self.sync_maximize_state()

    def _build_button(self, object_name: str, tooltip: str) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName(object_name)
        button.setIconSize(QSize(_BUTTON_ICON_PX, _BUTTON_ICON_PX))
        button.setFixedSize(WINDOW_BUTTON_WIDTH_PX, HEADER_BUTTON_SIZE_PX)
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        self.layout().addWidget(button)
        return button

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """窗口最大化状态变化后同步“最大化/还原”图标与提示。"""
        if watched is self._window and event.type() is QEvent.Type.WindowStateChange:
            self.sync_maximize_state()
        return False

    def toggle_maximized(self) -> None:
        """在最大化与还原之间切换窗口。"""
        toggle_maximized(self._window)

    def sync_maximize_state(self) -> None:
        """按窗口当前状态切换“最大化/还原”的图标与提示。"""
        maximized = self._window.isMaximized()
        self.maximize_button.setIcon(svg_icon("window-restore" if maximized else "window-maximize"))
        self.maximize_button.setToolTip("还原" if maximized else "最大化")


def enable_custom_title_bar(window: QWidget) -> None:
    """去掉系统标题栏但保留原生边框，使客户区覆盖标题行区域。"""
    if not _WINDOWS:
        return
    api = _api()
    hwnd = int(window.winId())
    style = api.get_long(hwnd, _GWL_STYLE)
    api.set_long(hwnd, _GWL_STYLE, style & ~_WS_CAPTION)
    api.user32.SetWindowPos(
        hwnd,
        None,
        0,
        0,
        0,
        0,
        _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_FRAMECHANGED,
    )


def apply_window_theme(window: QWidget, *, is_dark: bool) -> None:
    """按解析后的主题同步 DWM 边框观感：深色边框、Win11 圆角与描边颜色。

    沉浸式深色属性主要由 Qt 平台插件按 ``apply_theme()`` 声明的配色方案维护，
    这里直写一份作为兜底（含 Win10 1903 前的旧属性 id 回落），避免保留
    ``WS_THICKFRAME`` 后系统按浅色绘制边框、深色主题下露出白色窗缘；窗口的
    1 像素边框描边另有独立属性且系统默认偏浅（深色主题下顶部呈浅色细线），
    改为跟随主题的窗口底色后与界面融为一体。属性失败（旧系统不支持该 id、
    离屏假窗口句柄或圆角偏好缺失）时静默降级，包括 ctypes 把失败 HRESULT
    转成的 ``OSError``，不影响任何其它行为。
    """
    if not _WINDOWS:
        return
    hwnd = int(window.winId())
    if hwnd == 0:
        # 离屏等平台窗口没有真实句柄，DWM 调用必然失败，提前返回。
        return
    api = _api()
    value = 1 if is_dark else 0
    if not _set_dwm_dword(api, hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, value):
        # Win10 1903 之前的系统只认识旧的属性 id，任一成功即可。
        _set_dwm_dword(api, hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, value)
    # 圆角偏好与描边颜色仅 Windows 11 支持，旧系统返回错误码时忽略。
    _set_dwm_dword(api, hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE, _DWMWCP_ROUND)
    _set_dwm_dword(api, hwnd, _DWMWA_BORDER_COLOR, _border_colorref(is_dark))


def _border_colorref(is_dark: bool) -> int:
    """窗口边框描边的 COLORREF（``0x00BBGGRR``）：取主题的窗口底色。

    描边与客户区底色一致后既不会在深色主题下露出浅色细线，也保留窗口轮廓；
    浅色主题同样统一取窗口底色，两个主题观感一致。
    """
    window_color = tokens("dark" if is_dark else "light").window
    red = int(window_color[1:3], 16)
    green = int(window_color[3:5], 16)
    blue = int(window_color[5:7], 16)
    return red | green << 8 | blue << 16


def _set_dwm_dword(api: _Api, hwnd: int, attribute: int, value: int) -> bool:
    """写入一个 DWORD 型 DWM 窗口属性，返回是否被系统接受。

    ctypes 的 restype 为 ``HRESULT`` 时失败返回值会被自动转换成 ``OSError``，
    必须一并视为"属性未被接受"而不是向外抛出。
    """
    holder = ctypes.c_int(value)
    try:
        result = api.dwm_set_window_attribute(
            hwnd,
            attribute,
            ctypes.cast(ctypes.byref(holder), ctypes.c_void_p),
            ctypes.sizeof(holder),
        )
    except OSError:
        return False
    return result == 0


def handle_native_event(
    window: QWidget, event_type: bytes, message: object
) -> tuple[bool, int] | None:
    """处理 ``WM_NCCALCSIZE`` 与 ``WM_NCHITTEST``；返回 None 表示交回默认处理。"""
    if not _WINDOWS or event_type != _GENERIC_MSG:
        return None
    msg = _MSG.from_address(int(message))
    if msg.message == _WM_NCCALCSIZE:
        return _handle_ncalc_size(msg)
    if msg.message == _WM_NCHITTEST:
        return _handle_nchit_test(window, msg)
    return None


def _handle_ncalc_size(msg: _MSG) -> tuple[bool, int] | None:
    """最大化时把客户区固定为显示器工作区，避免边框缝隙与任务栏遮挡。

    只用消息自带的 ``hwnd``（不调用 ``QWidget.winId()``，窗口创建期的原生
    消息会重入 ``nativeEvent``）。
    """
    if not msg.wParam:
        return None
    api = _api()
    if not api.user32.IsZoomed(msg.hwnd):
        # 普通状态交给默认处理：客户区即窗口矩形去掉原生边框（保留缩放条）。
        return None
    monitor = api.user32.MonitorFromWindow(msg.hwnd, _MONITOR_DEFAULTTONEAREST)
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(_MONITORINFO)
    if not api.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    params = _NCCALCSIZE_PARAMS.from_address(msg.lParam)
    params.rgrc[0] = info.rcWork
    return True, 0


def _handle_nchit_test(window: QWidget, msg: _MSG) -> tuple[bool, int] | None:
    """标签行空白处返回 HTCAPTION，获得原生拖动与双击最大化行为。

    命中判定用窗口内几何（``childAt``）而不是 ``QApplication.widgetAt``：
    后者依赖窗口层叠与真实鼠标位置，无法在测试里稳定复现，且高 DPI 下
    还要额外的坐标系换算。
    """
    api = _api()
    x = ctypes.c_short(msg.lParam & 0xFFFF).value
    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
    point = _POINT(x, y)
    if not api.user32.ScreenToClient(msg.hwnd, ctypes.byref(point)):
        return None
    ratio = window.devicePixelRatio() or 1.0
    local = QPoint(round(point.x / ratio), round(point.y / ratio))
    tab_bar = getattr(window, "tab_bar", None)
    if not isinstance(tab_bar, QTabBar):
        return None
    under_cursor = window.childAt(local)
    if is_title_drag_point(under_cursor, tab_bar=tab_bar, pos=tab_bar.mapFrom(window, local)):
        return True, _HTCAPTION
    return None


def is_title_drag_point(
    widget_under_cursor: QWidget | None, *, tab_bar: QTabBar, pos: QPoint
) -> bool:
    """命中点是否位于标签行空白处（应作为 HTCAPTION 拖动窗口）。

    ``widget_under_cursor`` 是窗口内命中的最深子控件（``QWidget.childAt()``
    的结果），``pos`` 是相对标签栏的坐标。命中标签本身、“+”新建按钮、滚动
    按钮或其它控件时返回 False，点击仍按普通客户区事件处理。
    """
    if widget_under_cursor is not tab_bar:
        return False
    return tab_bar.tabAt(pos) < 0


def toggle_maximized(window: QWidget) -> None:
    """在最大化与还原之间切换窗口。"""
    if window.isMaximized():
        window.showNormal()
    else:
        window.showMaximized()


# Linux 无边框窗口的缩放带宽度（像素）。与 Windows 的 WS_THICKFRAME 相近，
# 太窄难以命中，太宽会抢占边缘控件的点击。
_RESIZE_MARGIN_PX = 6

# GTK 客户端请求窗口管理器弹出系统窗口菜单的 ClientMessage 名称；GNOME、
# KDE、XFCE 等主流窗口管理器均实现，菜单内容与系统标题栏右键一致。
_GTK_SHOW_WINDOW_MENU = b"_GTK_SHOW_WINDOW_MENU"

_CLIENT_MESSAGE = 33
_SUBSTRUCTURE_REDIRECT_MASK = 1 << 20
_SUBSTRUCTURE_NOTIFY_MASK = 1 << 19


def resize_edges_for(pos: QPoint, size: QSize, margin: int = _RESIZE_MARGIN_PX) -> Qt.Edge | None:
    """返回命中缩放带的窗口边缘组合；不在任何边缘时返回 None。"""
    edges = Qt.Edge(0)
    if pos.x() <= margin:
        edges |= Qt.Edge.LeftEdge
    elif pos.x() >= size.width() - 1 - margin:
        edges |= Qt.Edge.RightEdge
    if pos.y() <= margin:
        edges |= Qt.Edge.TopEdge
    elif pos.y() >= size.height() - 1 - margin:
        edges |= Qt.Edge.BottomEdge
    return edges if edges else None


def _resize_cursor(edges: Qt.Edge) -> Qt.CursorShape:
    """按边缘组合返回缩放光标形状。"""
    horizontal = edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge)
    vertical = edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge)
    if horizontal and vertical:
        # 左上与右下为反斜向，右上与左下为斜向（与 Windows 一致）。
        if (edges & Qt.Edge.LeftEdge and edges & Qt.Edge.TopEdge) or (
            edges & Qt.Edge.RightEdge and edges & Qt.Edge.BottomEdge
        ):
            return Qt.CursorShape.SizeFDiagCursor
        return Qt.CursorShape.SizeBDiagCursor
    if horizontal:
        return Qt.CursorShape.SizeHorCursor
    return Qt.CursorShape.SizeVerCursor


class _XClientMessageEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("message_type", ctypes.c_ulong),
        ("format", ctypes.c_int),
        ("data", ctypes.c_long * 5),
    ]


class _XEvent(ctypes.Union):
    _fields_ = [
        ("type", ctypes.c_int),
        ("xclient", _XClientMessageEvent),
        ("pad", ctypes.c_long * 24),
    ]


@lru_cache(maxsize=1)
def _x11_library() -> ctypes.CDLL:
    """懒加载 libX11 并声明本模块用到的函数签名。"""
    lib = ctypes.CDLL("libX11.so.6")
    lib.XInternAtom.restype = ctypes.c_ulong
    lib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.XDefaultRootWindow.restype = ctypes.c_ulong
    lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    lib.XSendEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_int,
        ctypes.c_long,
        ctypes.c_void_p,
    ]
    lib.XFlush.argtypes = [ctypes.c_void_p]
    return lib


def _send_x11_window_menu(window: QWidget, global_pos: QPoint) -> bool:
    """请求 X11 窗口管理器在指定位置弹出系统窗口菜单。

    复用 Qt 已打开的 X11 Display 发送 ``_GTK_SHOW_WINDOW_MENU``
    ClientMessage（与 GTK 的行为一致），菜单内容就是系统标题栏右键菜单。
    ``XSendEvent`` 无法确认窗口管理器是否响应，因此仅在连接、原子或窗口 ID
    不可用时返回 False 并回退自绘菜单。
    """
    app = QApplication.instance()
    if app is None or app.platformName() != "xcb":
        return False
    try:
        display = app.nativeInterface().display()
        window_id = int(window.winId())
    except (AttributeError, RuntimeError, TypeError):
        return False
    if not display or not window_id:
        return False
    lib = _x11_library()
    display_ptr = ctypes.c_void_p(display)
    atom = lib.XInternAtom(display_ptr, _GTK_SHOW_WINDOW_MENU, 0)
    if not atom:
        return False
    event = _XEvent()
    event.xclient.type = _CLIENT_MESSAGE
    event.xclient.send_event = 1
    event.xclient.display = display_ptr
    event.xclient.window = window_id
    event.xclient.message_type = atom
    event.xclient.format = 32
    event.xclient.data[0] = 0  # timestamp：0 等同 CurrentTime
    event.xclient.data[1] = global_pos.x()
    event.xclient.data[2] = global_pos.y()
    root = lib.XDefaultRootWindow(display_ptr)
    lib.XSendEvent(
        display_ptr,
        root,
        0,
        _SUBSTRUCTURE_REDIRECT_MASK | _SUBSTRUCTURE_NOTIFY_MASK,
        ctypes.byref(event),
    )
    lib.XFlush(display_ptr)
    return True


def build_window_menu(window: QWidget) -> QMenu:
    """构建无边框窗口的备用窗口菜单（原生菜单不可用时兜底）。"""
    menu = QMenu(window)
    menu.addAction("最小化").triggered.connect(window.showMinimized)
    toggle = menu.addAction("还原" if window.isMaximized() else "最大化")
    toggle.triggered.connect(lambda: toggle_maximized(window))
    menu.addAction("关闭").triggered.connect(window.close)
    return menu


def show_window_menu(window: QWidget, global_pos: QPoint) -> None:
    """显示窗口菜单：优先请求 X11 系统原生菜单，其余情况弹出备用菜单。"""
    if _send_x11_window_menu(window, global_pos):
        return
    build_window_menu(window).exec(global_pos)


class _LinuxTitleBarFilter(QObject):
    """Linux 无边框窗口的标签行过滤器：拖动、双击最大化与右键窗口菜单。"""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._window = window
        self._tab_bar: QTabBar | None = None
        tab_bar = getattr(window, "tab_bar", None)
        if isinstance(tab_bar, QTabBar):
            self._tab_bar = tab_bar
            tab_bar.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if self._tab_bar is None or watched is not self._tab_bar:
            return False
        if isinstance(event, QContextMenuEvent):
            return self._handle_context_menu(event)
        if isinstance(event, QMouseEvent) and event.button() is Qt.MouseButton.LeftButton:
            return self._handle_mouse(event)
        return False

    def _handle_context_menu(self, event: QContextMenuEvent) -> bool:
        if not is_title_drag_point(self._tab_bar, tab_bar=self._tab_bar, pos=event.pos()):
            return False
        show_window_menu(self._window, event.globalPos())
        return True

    def _handle_mouse(self, event: QMouseEvent) -> bool:
        pos = event.position().toPoint()
        if not is_title_drag_point(self._tab_bar, tab_bar=self._tab_bar, pos=pos):
            return False
        if event.type() is QEvent.Type.MouseButtonPress:
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
                return True
        elif event.type() is QEvent.Type.MouseButtonDblClick:
            toggle_maximized(self._window)
            return True
        return False


class _LinuxResizeFilter(QObject):
    """应用级过滤器：在无边框窗口四边/四角实现原生缩放与光标反馈。"""

    def __init__(self, window: QWidget) -> None:
        super().__init__(window)
        self._window = window
        self._override_active = False
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        self._ensure_hover_tracking(watched)
        etype = event.type()
        if watched is self._window and etype in {
            QEvent.Type.Hide,
            QEvent.Type.Close,
            QEvent.Type.WindowStateChange,
        }:
            self._clear_cursor()
            return False
        if self._window.isMaximized() or not self._window.isVisible():
            self._clear_cursor()
            return False
        if etype is QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            if event.button() is Qt.MouseButton.LeftButton:
                edges = self._edges_at(watched, event)
                if edges is not None:
                    handle = self._window.windowHandle()
                    if handle is not None:
                        handle.startSystemResize(edges)
                        return True
        elif etype in {QEvent.Type.MouseMove, QEvent.Type.HoverMove} and isinstance(
            event, QMouseEvent
        ):
            self._update_cursor(self._edges_at(watched, event))
        elif etype is QEvent.Type.Leave:
            self._clear_cursor()
        return False

    def _edges_at(self, watched: QObject, event: QMouseEvent) -> Qt.Edge | None:
        """把事件坐标换算到窗口坐标后判断缩放带。

        Wayland 没有全局坐标，不能用 ``globalPosition()`` 反算，因此统一
        用接收控件的局部坐标 ``mapTo`` 到窗口。
        """
        if isinstance(watched, QWidget):
            local = watched.mapTo(self._window, event.position().toPoint())
        else:
            local = event.position().toPoint()
        return resize_edges_for(local, self._window.size())

    def _ensure_hover_tracking(self, watched: QObject) -> None:
        """为事件经过的控件开启悬停追踪，保证边缘光标能实时反馈。"""
        if not isinstance(watched, QWidget):
            return
        if not watched.hasMouseTracking():
            watched.setMouseTracking(True)
        if not watched.testAttribute(Qt.WidgetAttribute.WA_Hover):
            watched.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def _update_cursor(self, edges: Qt.Edge | None) -> None:
        if edges is None:
            self._clear_cursor()
            return
        desired = QCursor(_resize_cursor(edges))
        current = QApplication.overrideCursor()
        if self._override_active and current is not None and current.shape() == desired.shape():
            return
        self._clear_cursor()
        QApplication.setOverrideCursor(desired)
        self._override_active = True

    def _clear_cursor(self) -> None:
        if self._override_active:
            QApplication.restoreOverrideCursor()
            self._override_active = False


def enable_linux_custom_title_bar(window: QWidget) -> None:
    """Linux 下去掉系统标题栏，标签行兼作标题行。

    与 Windows 的 ``WS_CAPTION`` 方案等价：``FramelessWindowHint`` 去掉系统
    装饰，拖动、双击最大化、边缘缩放与右键窗口菜单分别由两个事件过滤器
    补回；窗口按钮由 ``MainWindow`` 装配到标签行右上角。
    """
    if _WINDOWS or not sys.platform.startswith("linux"):
        return
    window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    window.setMouseTracking(True)
    window.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    _LinuxTitleBarFilter(window)
    _LinuxResizeFilter(window)
