# 第三方依赖声明

QSerialTool 使用或计划使用以下第三方组件。正式发布时还应包含依赖发行包提供的完整许可证文本，并根据锁文件补齐所有传递依赖。

| 组件 | 计划版本约束 | 用途 | 许可证 | 来源 |
|---|---|---|---|---|
| PySide6 | `>=6.8,<7` | Qt for Python 桌面界面 | LGPL-3.0 / GPL-3.0 / 商业许可 | https://pypi.org/project/PySide6/ |
| pyserial | `==3.5` | 串口访问 | BSD-3-Clause | https://pypi.org/project/pyserial/ |
| PyInstaller | `>=6.20,<7` | 单文件打包 | GPL-2.0-or-later，附带 Bootloader Exception | https://pypi.org/project/pyinstaller/ |
| pytest | `>=8,<10` | 测试框架 | MIT | https://pypi.org/project/pytest/ |
| pytest-qt | `>=4.4,<5` | Qt UI 测试 | MIT | https://pypi.org/project/pytest-qt/ |
| pytest-cov | `>=6,<8` | 覆盖率集成 | MIT | https://pypi.org/project/pytest-cov/ |
| coverage.py | 由 pytest-cov 解析 | 覆盖率统计 | Apache-2.0 | https://pypi.org/project/coverage/ |
| Ruff | `>=0.9,<1` | 格式化与静态检查 | MIT | https://pypi.org/project/ruff/ |
| pip-tools | `>=7.4,<8` | 生成锁定依赖 | BSD-3-Clause | https://pypi.org/project/pip-tools/ |
| setuptools | `>=77,<85` | 构建后端 | MIT | https://pypi.org/project/setuptools/ |
| wheel | `>=0.42` | Python wheel 构建 | MIT | https://pypi.org/project/wheel/ |

## 分发注意事项

- PySide6 和 Qt 的实际许可证取决于具体使用方式；公开分发前必须确认 LGPL 或商业许可要求。
- PyInstaller 的许可证例外适用于其 bootloader；打包应用仍需保留相关声明。
- 本项目采用 MIT 许可证，不改变第三方组件各自的许可证。