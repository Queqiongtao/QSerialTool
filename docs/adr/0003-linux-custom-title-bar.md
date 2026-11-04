# ADR-0003：Linux 无边框窗口与自绘标题行

- 状态：Accepted
- 日期：2026-10-18
- 决策范围：Linux 桌面平台的窗口装饰与标题行行为

## 背景

ADR-0002 的“标签行兼作标题栏”基于 WinAPI（去掉 `WS_CAPTION`、保留
`WS_THICKFRAME`，配合 `WM_NCCALCSIZE`/`WM_NCHITTEST`），结论是“只适用于
Windows；其它平台保持系统标题栏”。实际使用中出现预期偏差：Ubuntu 下是
“系统标题栏 + 应用标签行”两行，且最小化/最大化/关闭按钮不与标签同行，
与 Windows 的单行布局不一致。需求是两平台布局一致，不要求逐像素相同。

## 候选方案

1. 保持系统标题栏：零风险，但布局差异无法消除，与需求冲突。
2. `FramelessWindowHint` 去装饰，用 Qt 的 `startSystemMove()` /
   `startSystemResize()` 加事件过滤器补回拖动、双击最大化、边缘缩放与
   窗口菜单：xcb 与 wayland 都可用，跨桌面差异交给 Qt 与合成器。
3. 只隐藏标题、保留系统缩放边框：X11/Wayland 均无稳定协议支持“部分装饰”，
   不可行。

## 决策

采用方案 2，Linux 的 `xcb` 与 `wayland` 会话都启用。

- 平台判定集中在 `window_chrome.uses_custom_title_bar()`：Windows 桌面或
  Linux 的 `xcb`/`wayland` 返回 True；离屏平台返回 False，测试保持普通
  窗口路径。
- `enable_linux_custom_title_bar()` 设置 `FramelessWindowHint`；窗口按钮复用
  `WindowButtons`，由 `MainWindow` 装配到标签行右上角，形成与 Windows 一致
  的单行标题行。
- `_LinuxTitleBarFilter` 处理标签行空白：按住拖动走
  `QWindow.startSystemMove()`，双击在最大化与还原间切换；标签点击、双击
  重命名、“+”、滚动按钮与“☰”菜单等控件事件不受影响。
- `_LinuxResizeFilter` 是应用级事件过滤器：在窗口四边/四角 6 像素内按下时
  调用 `startSystemResize()`，并用 `QApplication` 覆盖光标反馈缩放方向；
  窗口隐藏、关闭或状态变化时恢复光标。
- 右键标签行空白弹出窗口菜单：xcb 下复用 Qt 已打开的 X11 Display 发送
  `_GTK_SHOW_WINDOW_MENU` ClientMessage，由窗口管理器弹出系统原生菜单
  （GNOME/KDE/XFCE 均实现，与系统标题栏右键一致）；Wayland 原生会话或
  原子/窗口 ID 不可用时回退 `build_window_menu()` 的自绘菜单。
- Windows 的 ADR-0002 路径不变：`uses_native_chrome()`、`nativeEvent()`、
  `keep_window_hidden()`、DWM 主题钩子仍只作用于 Windows。

## 后果

优点：

- Windows 与 Linux 的窗口布局一致，标签、工具按钮与窗口按钮同一行。
- 拖动、最大化与缩放复用 Qt 的跨平台系统移动/缩放接口，不依赖具体的
  窗口管理器私有协议；xcb 下右键菜单仍是系统原生菜单。

约束与取舍：

- 无系统窗口阴影：xcb 下窗口管理器不再为无边框窗口提供边框阴影，wayland
  下由合成器决定；如需阴影需自绘，当前未实现。
- Wayland 原生会话没有公开接口请求合成器窗口菜单，右键为应用自绘菜单，
  外观与 GNOME 系统菜单不同。
- 边缘缩放依赖 `startSystemResize()`，个别合成器可能不支持或行为受限。
- 无边框窗口的真实拖动/缩放/菜单手势无法离屏自动化，交付前需在
  X11（Xwayland）与 Wayland 会话人工验收。
