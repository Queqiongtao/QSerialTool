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

- [ ] 在 Ubuntu 22.04 执行 `scripts/build.sh`。
- [ ] 单文件具有执行权限并可冷启动。
- [ ] Qt `xcb` 平台插件加载正常。
- [ ] 窗口图标正确，浅色与深色外观无破版且控件文字对比度可读。
- [ ] 完成串口权限、权限错误提示和两小时稳定性测试。

## 发布产物

- [x] Windows 单文件和 SHA-256 已生成。
- [ ] Linux 单文件和 SHA-256 已生成。
- [x] 发布说明列出已知限制。
- [x] 发布说明注明 Windows/Linux 必须分别构建。
