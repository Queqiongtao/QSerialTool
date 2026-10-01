# QSerialTool

QSerialTool 是一个面向开发者与测试人员的跨平台串口调试助手。项目计划支持多标签串口会话、文本与 HEX 收发、日志导出、周期发送，以及 Windows 和 Linux 单文件分发。

> 远程仓库：<https://github.com/Queqiongtao/QSerialTool>

## 当前状态

工程当前已完成 **M1：核心领域实现**，下一步进入 **M2：串口链路**。

已完成：

- M0：建立规范化目录、Python 包结构、依赖锁、质量工具和许可证声明。
- M1：实现串口配置、状态机、错误模型、HEX/文本编解码、换行策略和有界记录缓冲。

当前尚未实现真实串口通信、Worker、会话控制器或图形界面。

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