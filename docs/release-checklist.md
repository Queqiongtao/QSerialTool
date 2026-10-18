# QSerialTool 发布检查清单

## 代码和文档

- [x] 版本号与发布说明一致（当前 `0.1.0`）。
- [x] `README.md`、`LICENSE`、`THIRD_PARTY_NOTICES.md` 完整。
- [x] `docs/user-guide.md`、`docs/developer-guide.md` 和 `docs/README.md` 完整。
- [x] `AGENT.md`、实施计划和架构决策记录已同步，提交信息与文档使用简体中文。
- [x] 本地 Hook 已启用，文档同步检查通过。
- [x] 提交信息中文检查（本地 `commit-msg` 钩子或 CI）通过。
- [x] GitHub Actions 文档、Ruff 和 pytest 门禁通过（2026-10-17 起 Python 3.10–3.13 全部通过）。
- [x] 工作区干净，目标提交已推送。

## 自动化质量门禁

- [x] `ruff format --check .` 通过。
- [x] `ruff check .` 通过。
- [x] `pytest` 通过。
- [x] domain 分支覆盖率不低于 90%。
- [x] application 分支覆盖率不低于 90%。
- [x] 标准 wheel 和 sdist 构建成功。

## Windows 验收

- [x] `scripts/build.bat` 在干净环境成功。
- [x] 生成 `QSerialTool.exe` 和 SHA-256。
- [x] 单文件在未安装 Python 的干净 Windows 测试机启动（2026-10-17 已验收）。
- [x] 无缺失 Qt 插件（本机单文件启动验证）。
- [x] 窗口、任务栏与 `QSerialTool.exe` 图标显示正确（本机核对）。
- [x] 配置文件可在用户 AppData 创建并恢复标签（本机核对）。
- [x] 完成真实串口收发、错误和长时间稳定性测试（2026-10-18，详见下方「Windows 硬件验收记录」）。

## Windows 硬件验收记录

2026-10-18 在本机完成，硬件为两个交叉接线（TX↔RX、共地）的 USB 转串口模块：
应用端口 `COM21`（USB-SERIAL CH340）、对端 `COM5`（USB-Enhanced-SERIAL CH343）。

- **自动化硬件用例**（`QSERIALTOOL_HW_PORTS=COM21,COM5 pytest -m hardware`，9 项全部通过）：
  文本/HEX 字节一致、GB18030 中文双向、波特率矩阵（9600/115200/921600）、
  高频接收与暂停恢复、周期发送停止、端口占用错误、921600 全双工压力 600 秒、
  1 MiB 二进制完整性（含断开时跨块解码尾巴补记校验）。
- **2 小时连续接收**（源码运行、进程内采样）：125 分钟持续接收，自动日志连续
  写盘（47 MiB+），句柄 252→254 全程稳定，界面文档窗口封顶 2003 块。
- **缓冲上限与内存平台化**（满速 921600，实测约 93 KB/s）：持续注入 166.7 MB，
  缓冲在 32 MiB 上限钉住（记录数 4096 恒定），累计淘汰 16,082 条；触顶后
  18.7 分钟观察窗私有内存 230.7 → 231.0 MiB（+0.3 MB），内存有界且平台化；
  全程零 I/O 错误，自动日志累计 631 MiB。
- **已知特征（跟进项，不阻塞发布）**：
  `LogRecord` 预生成 `hex_text`（原始字节的 3 倍）使缓冲内存放大约 5.5 倍，
  32 MiB 上限对应的稳态私有内存约 231 MiB（文本模式会同时保留 text 与 hex_text）；
  CH34x 驱动约 16 ms 的 URB 延迟会把小包写入节流到约 9 KB/s，大块写入不受影响。

## Linux 验收

- [x] 在 Ubuntu 22.04 执行 `scripts/build.sh`。
- [x] 单文件具有执行权限并可冷启动。
- [x] Qt `xcb` 平台插件加载正常。
- [x] 窗口图标正确，浅色与深色外观无破版且控件文字对比度可读。
- [x] 完成串口权限、权限错误提示和两小时稳定性测试（虚拟串口降级验收，
  详见下方「Linux 验收记录」）。

## Linux 验收记录

2026-10-18 在 Ubuntu 22.04.5 LTS（内核 6.8.0-138，VMware 虚拟机，glibc 2.35，
Python 3.10.12，PySide6 6.11.2 按 `requirements.lock`）执行，同机同时承担构建与
验收；本机已装 Python，因此干净环境以 `env -i` 空环境近似。

- **构建**：`./scripts/build.sh` 依次通过文档同步、Ruff、pytest（507 passed,
  16 skipped）、PyInstaller 单文件与 SHA-256 生成；产物大小 66,493,936 字节，
  SHA-256 `dc97ae490b3f7be09e04270bbea44d289620b7d913c553e80b2058a8619eec94`，
  详见 `docs/build-and-release.md`。
- **冷启动**：`env -i HOME=… DISPLAY=:0 XDG_RUNTIME_DIR=… LANG=zh_CN.UTF-8
  QT_QPA_PLATFORM=xcb ./dist/QSerialTool` 在无 `PATH`、无系统 Python 依赖的环境下
  成功创建窗口；`~/.config/QSerialTool/settings.json` 与
  `~/.config/QSerialTool/logs/app.log` 自动创建，配置文件可恢复窗口与主题。
  单文件自带解释器，未在未装 Python 的独立干净系统复验。
- **xcb 插件**：单文件解包目录包含 `PySide6/Qt/plugins/platforms/libqxcb.so`，
  `ldd` 无缺失库；`QT_QPA_PLATFORM=xcb` 启动成功。注意 Ubuntu 22.04 默认未安装
  Qt 6.5+ 所需的 `libxcb-cursor0`，安装后插件加载正常（已记入构建文档）。
- **外观**：浅色与深色主题各截图核对（`system`/`light`/`dark` 配置切换），无破版、
  控件文字对比度可读；中文字体行高较大时侧栏按设计出现滚动条。
- **窗口图标**：图标资源 `qserialtool.png`（256×256）与窗口图标对象加载正常；
  Xwayland 下 `_NET_WM_ICON` 为空（最小 Qt 程序同样复现），属环境限制，未能在
  任务栏截图核对。
- **桌面入口**：`scripts/install-desktop.sh` 安装到 `~/.local/share` 后，
  `desktop-file-validate` 通过，`gtk-launch qserialtool` 正常启动，窗口
  `WM_CLASS=QSerialTool` 与 `StartupWMClass` 匹配；`--uninstall` 可清理；
  裸 `dist/QSerialTool` 在文件管理器中仍显示通用图标（Linux 机制，见已知限制）。
- **标题行**：Linux 下用 `FramelessWindowHint` 去掉系统标题栏，标签行与
  最小化/最大化（还原）/关闭按钮同一行，拖动、空白双击最大化、四边/四角
  缩放与右键窗口菜单由事件过滤器补回；Xwayland 下经 `xwininfo`/`xprop`
  确认窗口未被 WM 加框（无 `_NET_FRAME_EXTENTS`）、`_GTK_SHOW_WINDOW_MENU`
  发送成功并可请求系统原生菜单；Wayland 原生会话启动正常。真实鼠标手势
  无法脚本化，需人工在 X11 与 Wayland 会话确认（见已知限制）。
- **串口验收（虚拟串口降级）**：本机无 USB 转串口硬件，使用两个 PTY 双向桥接
  模拟交叉接线，对端脚本回显/发送；验收进程内对 pyserial 仅做两项测试限定补丁：
  忽略 PTY 不支持的 DTR/RTS modem ioctl、模拟独占打开以复现端口占用。运行
  `QSERIALTOOL_HW_PORTS=<app>,<peer> pytest -m hardware`，9 项全部通过（613.35 s）：
  文本/HEX 字节一致、GB18030 中文、波特率矩阵、高频接收与暂停恢复、周期发送停止、
  端口占用错误、921600 全双工压力 600 s、1 MiB 二进制完整性。
- **串口权限与提示**：对 `chmod 000` 的 PTY 从设备发起连接，会话进入错误态并弹窗
  显示权限错误，追加中文建议“请检查设备权限或用户所在系统用户组。”，端口配置保留；
  为此在 `SessionTab` 错误弹窗中补充展示 `suggestion`，并新增单元测试覆盖。
- **两小时稳定性**：源码运行、虚拟串口持续接收 7200 s，rx 39,511,080 字节，记录
  缓冲封顶 100,000 条；5 分钟基线私有内存 87.8 MiB，峰值 273.9 MiB，封顶后
  11.5 分钟观测窗 272.4–273.9 MiB（波动 1.5 MiB），工作集 308.8 MiB；自动 CSV
  日志累计 155.5 MiB；诊断日志零 ERROR/WARNING。`monitor_serialtool.py` 默认阈值
  （热身 5 分钟后增长 ≤50 MiB）对“从空缓冲填充到封顶”的曲线判 FAIL，属阈值语义
  不适用，按封顶后平台期人工判定 PASS。
- **已知限制**：未使用真实 USB 转串口硬件，运行中拔插、真实驱动差异等
  实施计划 §17.5 必测场景未覆盖；Xwayland 不暴露 `_NET_WM_ICON`；验收机已装
  Python，未做独立纯净系统冷启动；Linux 裸 ELF 无法内嵌文件图标，桌面图标
  需安装 `.desktop` 入口，不提供 AppImage/Flatpak；Linux 无边框窗口无系统
  阴影，Wayland 原生会话的标题行右键为应用自绘菜单，拖动/缩放手势需人工
  验收。

## 发布产物

- [x] Windows 单文件和 SHA-256 已生成。
- [x] Linux 单文件和 SHA-256 已生成。
- [x] 发布说明列出已知限制。
- [x] 发布说明注明 Windows/Linux 必须分别构建。
