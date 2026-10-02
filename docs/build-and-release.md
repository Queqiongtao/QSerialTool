# QSerialTool 构建与发布

## 适用环境

- Windows 10/11 x64。
- Ubuntu 22.04 x64 或兼容的 Linux x64 环境。
- Python 3.10.x。
- 已按 README 创建 `.venv` 并安装 `[dev,build]` 依赖。

Windows 和 Linux 必须在对应操作系统上分别构建，不能交叉生成单文件程序。

## Windows 构建

在 PowerShell 中运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

脚本依次执行：

1. Ruff 格式检查。
2. Ruff 静态检查。
3. pytest 全部测试。
4. PyInstaller 单文件构建。
5. 生成 SHA-256 校验文件。

产物：

```text
dist/QSerialTool.exe
dist/QSerialTool.exe.sha256
```

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

## 运行依赖

Windows 单文件目标机器无需安装 Python。Linux 单文件仍依赖常见图形和系统运行库；若启动时报 Qt 平台插件错误，请根据发行版安装 XCB 相关系统库。

## 单文件行为

- 首次启动会解压到系统临时目录，启动速度慢于普通源码运行。
- 临时目录不可执行或磁盘空间不足时可能无法启动。
- 程序不包含自动更新、代码签名和遥测功能。
- 发布时必须同时提供对应的 SHA-256 校验值。

## 当前 Windows 构建记录

2026-10-02 已成功生成：

- 文件：`dist/QSerialTool.exe`
- 大小：44376481 字节
- SHA-256：`f5d8ab6dff8f49c68f3a80047604019d175f67708791e8284f23a150c7c2e6a7`
- 当前执行环境受 Application Control 策略限制，无法直接启动该外部可执行文件；需要在允许执行本地构建产物的测试机上完成启动验收。
