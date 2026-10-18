# QSerialTool 构建与发布

## 适用环境

- Windows 10/11 x64。
- Ubuntu 22.04 x64 或兼容的 Linux x64 环境。
- Python 3.10.x–3.13.x。
- 已按 README 创建 `.venv` 并安装 `[dev,build]` 依赖。

Windows 和 Linux 必须在对应操作系统上分别构建，不能交叉生成单文件程序。

## Windows 构建

双击 `scripts\build.bat`，或在终端运行：

```powershell
.\scripts\build.bat
```

`scripts\build.bat` 只是转调同目录的 `build.ps1`，两者等价；也可以直接调用 PowerShell 脚本：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

脚本依次执行：

1. 文档同步检查。
2. Ruff 格式检查。
3. Ruff 静态检查。
4. pytest 全部测试。
5. PyInstaller 单文件构建。
6. 生成 SHA-256 校验文件。

产物：

```text
dist/QSerialTool.exe
dist/QSerialTool.exe.sha256
```

重新构建前请先退出正在运行的本程序：运行中的单文件进程会锁定 `dist/QSerialTool.exe`，PyInstaller 覆盖旧产物时会报 `PermissionError: [WinError 5] 拒绝访问`。

## Linux 构建

在 Ubuntu 22.04 或兼容环境运行：

```bash
chmod +x scripts/build.sh
./scripts/build.sh
```

产物：

```text
dist/QSerialTool
dist/QSerialTool.sha256
```

## 文档同步与 CI

首次贡献前启用本地提交 Hook：

```powershell
git config core.hooksPath .githooks
```

提交时 Hook 检查暂存变更与受影响文档是否属于同一提交。构建脚本会检查当前工作区；GitHub Actions 会在 push 和 pull request 上重新检查提交范围，并运行 Ruff 与 pytest。CI 不构建或发布单文件产物，Windows/Linux 构建仍必须在对应系统执行。

## 运行依赖

Windows 单文件目标机器无需安装 Python。Linux 单文件仍依赖常见图形和系统运行库；若启动时报 Qt 平台插件错误，请根据发行版安装 XCB 相关系统库。

Ubuntu 22.04 默认没有 Qt 6.5 及以上 `xcb` 平台插件所需的 `libxcb-cursor0`，
未安装时会报“Could not load the Qt platform plugin xcb”。执行以下命令补齐：

```bash
sudo apt-get install -y libxcb-cursor0
```

其他发行版还需确保 `libxcb-xinerama0`、`libxkbcommon-x11-0`、`libegl1`、`libgl1`、
`libdbus-1-3`、`libfontconfig1`、`libglib2.0-0` 等基础图形库存在（CI 工作流
`.github/workflows/quality.yml` 列出了参考列表）。

## 单文件行为

- 首次启动会解压到系统临时目录，启动速度慢于普通源码运行。
- 临时目录不可执行或磁盘空间不足时可能无法启动。
- 程序不包含自动更新、代码签名和遥测功能。
- 发布时必须同时提供对应的 SHA-256 校验值。

## 图标与样式资源

应用图标与控件样式资源位于 `src/qserialtool/ui/assets/`：

- `qserialtool.png` / `qserialtool.ico`：窗口图标；Windows 单文件构建会同时把 ICO 写入可执行文件图标。
- `chevron-*.svg`、`check*.svg`：下拉箭头与勾选标记（含禁用态），由全局 QSS 引用。

这些文件通过 `packaging/qserialtool.spec` 的 `datas` 打进单文件产物（解包路径为 `qserialtool/ui/assets`），并在 `pyproject.toml` 的 `package-data` 中声明，保证源码安装同样可用。修改图标图形后运行 `.\.venv\Scripts\python.exe scripts\generate_icon.py` 重新生成 PNG/ICO，并与脚本一起提交。

## 当前 Windows 构建记录

2026-10-17 已成功生成并完成本机启动验证：

- 文件：`dist/QSerialTool.exe`
- 大小：44971847 字节
- SHA-256：`1e7e8a09d7148c9fb220a9760fc81639dbd6aca876da7fbc3684a0133247ee9b`
- 本机已能直接启动该产物（单文件解包、Qt 插件、窗口渲染与配置读写正常）；并已在未安装 Python 的干净 Windows 环境完成单文件冷启动验收（2026-10-17）。

## 当前 Linux 构建记录

2026-10-18 在 Ubuntu 22.04.5 LTS（内核 6.8.0-138，glibc 2.35，Python 3.10.12，
PySide6 6.11.2 按 `requirements.lock`）执行 `./scripts/build.sh`，文档同步、Ruff、
pytest（498 passed, 16 skipped）、PyInstaller 单文件与 SHA-256 全部通过：

- 文件：`dist/QSerialTool`
- 大小：66491128 字节
- SHA-256：`f284f69c1501971075e06fac1d67f8a049bae797d7d4598d597799695a906210`
- 已用 `env -i` 空环境（无 `PATH`）与 `QT_QPA_PLATFORM=xcb` 完成冷启动、`xcb`
  插件加载、配置/诊断日志创建和明暗主题截图核对；同机同时承担构建与验收，
  未在未安装 Python 的独立干净系统复验。
