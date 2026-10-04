# QSerialTool 文档索引

> 文档版本：1.1  
> 软件版本：0.1.0  
> 对应基线提交：`cb6c23a`  
> 更新时间：2026-10-04 18:23:19 CST（星期日）

## 文档职责

| 文档 | 目标读者 | 职责 |
|---|---|---|
| `README.md` | 所有用户和贡献者 | 项目概览、环境创建、源码运行、快速质量命令 |
| `docs/user-guide.md` | 最终用户和测试人员 | 当前版本的安装、连接、收发、日志、配置和故障排查 |
| `docs/developer-guide.md` | 维护者和贡献者 | 当前架构、公共接口、线程模型、数据流、存储格式和扩展流程 |
| `docs/implementation-plan.md` | 产品和工程维护者 | V1 需求、目标设计、验收标准和里程碑基线 |
| `docs/adr/` | 架构维护者 | 影响公共接口、数据格式、线程模型或发布方式的关键决策 |
| `docs/build-and-release.md` | 发布负责人 | 构建步骤、产物和运行要求 |
| `docs/release-checklist.md` | 发布负责人 | 发布前必须核验的自动化与人工检查项 |
| `AGENT.md` | 代理和开发者 | 工程约束、真相来源和完成定义 |

## 真相来源

- 当前代码是行为的最终事实来源，但必须由自动化测试和本目录文档准确描述。
- 当前实现及内部约束以 `developer-guide.md` 为准。
- 用户操作方式以 `user-guide.md` 为准。
- 尚未进入当前实现的需求以 `implementation-plan.md` 为准。
- 历史架构取舍以对应 ADR 为准，ADR 被替代时不得删除。

## 实时同步规则

任何提交都必须在同一提交中更新或新增至少一个文档，纯测试变更可豁免但须在提交说明中注明理由。代码、测试和文档的语言统一为简体中文：

- UI 行为变化：更新 `user-guide.md`；实现结构变化同时更新 `developer-guide.md`。
- domain/application 变化：更新 `developer-guide.md`；涉及架构决策时新增或更新 ADR。
- infrastructure 变化：按影响更新 `developer-guide.md` 或 `user-guide.md`。
- 构建、依赖和发布方式变化：更新构建文档、发布清单或第三方声明。
- `AGENT.md` 规则变化：同步更新 `implementation-plan.md`。
- 纯测试变更可豁免文档更新，但必须在提交说明中注明理由。

机器规则配置在 `doc-sync-rules.json`。启用本地 Hook（`pre-commit` 文档同步与 `commit-msg` 提交信息校验）：

```powershell
git config core.hooksPath .githooks
```

手动验证：

```powershell
.\.venv\Scripts\python.exe scripts\check_docs_sync.py --staged
.\.venv\Scripts\python.exe scripts\check_docs_sync.py --base origin/main
.\.venv\Scripts\python.exe scripts\check_docs_sync.py --working-tree
.\.venv\Scripts\python.exe scripts\check_commit_message.py
.\.venv\Scripts\python.exe scripts\check_commit_message.py --base origin/main
```

GitHub Actions 会在 push 和 pull request 上再次执行文档同步、提交信息中文校验、Ruff 和 pytest。机器检查只能保证相关文档被纳入同一变更、提交信息包含中文，内容准确性仍需代码审查确认。
