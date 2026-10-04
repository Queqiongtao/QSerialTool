# QSerialTool

QSerialTool 是一个面向开发者与测试人员的跨平台串口调试助手。项目计划支持多标签串口会话、文本与 HEX 收发、日志导出、周期发送，以及 Windows 和 Linux 单文件分发。

> 远程仓库：<https://github.com/Queqiongtao/QSerialTool>

## 当前状态

工程当前处于 **M5：发布质量**，M0-M4 功能已完成。

已完成：

- M0：建立规范化目录、Python 包结构、依赖锁、质量工具和许可证声明。
- M1：实现串口配置、状态机、错误模型、HEX/文本编解码、换行策略和有界记录缓冲。
- M2：实现 pyserial Transport、Worker 命令队列、会话控制器、会话管理器和 `loop://` 集成验证。
- M3：实现多标签主窗口、端口配置、连接控制、文本/HEX 接收显示与基础发送编辑。
- M4：实现 CSV/TXT 日志、配置恢复、发送历史、周期发送、主题切换和日志导出。
- M5：已加入 Windows/Linux 单文件构建脚本、PyInstaller 配置、发布文档和检查清单。

当前仍需在允许执行本地产物的 Windows 环境和 Ubuntu 22.04 上完成单文件启动、真实串口和长时间稳定性验收。
## 环境要求

- Python 3.10.x
- Windows 10/11 x64 或 Ubuntu 22.04 及以上 Linux x64
- Git

## 创建开发环境

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
```

### Linux

```bash
python3.10 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip setuptools wheel
./.venv/bin/python -m pip install -e ".[dev,build]"
```

## 生成依赖锁文件

使用 pip-tools 根据 `pyproject.toml` 解析并锁定依赖：

```powershell
.\.venv\Scripts\python.exe -m piptools compile --all-extras --output-file=requirements.lock pyproject.toml
```

Linux 环境将命令中的解释器路径替换为 `./.venv/bin/python`。

## 运行程序

```powershell
.\.venv\Scripts\python.exe -m qserialtool
```

Linux 环境使用 `./.venv/bin/python -m qserialtool`。
## 质量检查

提交前按以下顺序执行：

```powershell
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
```

## 构建单文件

Windows（双击 `scripts\build.bat`，或在终端执行）：

```powershell
.\scripts\build.bat
```

也可以直接调用底层脚本：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1
```

Linux：

```bash
chmod +x scripts/build.sh
./scripts/build.sh
```

详细步骤见 `docs/build-and-release.md`，发布检查项见 `docs/release-checklist.md`。
## 项目文档

- 完整使用手册：`docs/user-guide.md`
- 当前实现开发指南：`docs/developer-guide.md`
- 文档索引与同步规则：`docs/README.md`
- 详细实施计划：`docs/implementation-plan.md`
- 工程代理规范：`AGENT.md`
- 架构决策记录：`docs/adr/`

## 文档实时同步

任何提交都必须在同一提交中更新或新增至少一个文档（纯测试变更需在提交说明中注明豁免理由），提交信息与文档统一使用简体中文。首次克隆后启用本地 Hook（`pre-commit` 文档同步与 `commit-msg` 提交信息校验）：

```powershell
git config core.hooksPath .githooks
```

文档同步和提交信息检查也可手动执行：

```powershell
.\.venv\Scripts\python.exe scripts\check_docs_sync.py --staged
.\.venv\Scripts\python.exe scripts\check_commit_message.py
```

GitHub Actions 会在 push 和 pull request 上再次校验文档同步、提交信息、Ruff 和测试。

## 许可证

项目代码采用 MIT 许可证，详见 `LICENSE`。第三方组件及其许可证信息见 `THIRD_PARTY_NOTICES.md`。
