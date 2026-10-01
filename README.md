# QSerialTool

QSerialTool 是一个面向开发者与测试人员的跨平台串口调试助手。项目计划支持多标签串口会话、文本与 HEX 收发、日志导出、周期发送，以及 Windows 和 Linux 单文件分发。

> 远程仓库：<https://github.com/Queqiongtao/QSerialTool>

## 当前状态

工程当前已完成 **M4：完整 MVP**，下一步进入 **M5：发布质量**。

已完成：

- M0：建立规范化目录、Python 包结构、依赖锁、质量工具和许可证声明。
- M1：实现串口配置、状态机、错误模型、HEX/文本编解码、换行策略和有界记录缓冲。
- M2：实现 pyserial Transport、Worker 命令队列、会话控制器、会话管理器和 `loop://` 集成验证。
- M3：实现多标签主窗口、端口配置、连接控制、文本/HEX 接收显示与基础发送编辑。
- M4：实现 CSV/TXT 日志、配置恢复、发送历史、周期发送、主题切换和日志导出。

当前尚未完成正式发布所需的真实硬件跨平台验收、压力测试、单文件产物验证和发布文档。

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

## 项目文档

- 详细实施计划：`docs/implementation-plan.md`
- 工程代理规范：`AGENT.md`
- 架构决策记录：`docs/adr/`

## 许可证

项目代码采用 MIT 许可证，详见 `LICENSE`。第三方组件及其许可证信息见 `THIRD_PARTY_NOTICES.md`。