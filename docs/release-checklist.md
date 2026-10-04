# QSerialTool 发布检查清单

## 代码和文档

- [ ] 版本号与发布说明一致。
- [x] `README.md`、`LICENSE`、`THIRD_PARTY_NOTICES.md` 完整。
- [x] `docs/user-guide.md`、`docs/developer-guide.md` 和 `docs/README.md` 完整。
- [ ] `AGENT.md`、实施计划和架构决策记录已同步，提交信息与文档使用简体中文。
- [ ] 本地 Hook 已启用，文档同步检查通过。
- [ ] 提交信息中文检查（本地 `commit-msg` 钩子或 CI）通过。
- [ ] GitHub Actions 文档、Ruff 和 pytest 门禁通过。
- [ ] 工作区干净，目标提交已推送。

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
- [ ] 单文件在允许执行本地产物的干净 Windows 测试机启动。
- [ ] 无缺失 Qt 插件。
- [ ] 窗口、任务栏与 `QSerialTool.exe` 图标显示正确。
- [ ] 配置文件可在用户 AppData 创建并恢复标签。
- [ ] 完成真实串口收发、拔插、错误和两小时稳定性测试。

## Linux 验收

- [ ] 在 Ubuntu 22.04 执行 `scripts/build.sh`。
- [ ] 单文件具有执行权限并可冷启动。
- [ ] Qt `xcb` 平台插件加载正常。
- [ ] 窗口图标正确，浅色与深色外观无破版且控件文字对比度可读。
- [ ] 完成串口权限、权限错误提示和两小时稳定性测试。

## 发布产物

- [ ] Windows 单文件和 SHA-256 已生成。
- [ ] Linux 单文件和 SHA-256 已生成。
- [x] 发布说明列出已知限制。
- [x] 发布说明注明 Windows/Linux 必须分别构建。
