# QSerialTool 当前实现开发指南

> 文档版本：1.0  
> 软件版本：0.1.0  
> 对应基线提交：`cb6c23a`  
> 更新时间：2026-10-02 09:32:11 CST（星期五）  
> 适用读者：维护者、测试人员和参与扩展的开发者

## 1. 文档职责

本指南记录当前代码的实际结构、接口、数据流和运行约束，不代替产品规划文档：

- 产品范围与原始设计：`docs/implementation-plan.md`
- 当前用户操作：`docs/user-guide.md`
- 关键架构决策：`docs/adr/`
- 构建与发布：`docs/build-and-release.md`
- 当前行为最终真值：源码和自动化测试

实现、接口、线程模型、配置 schema 或日志格式发生变化时，必须在同一提交中更新本指南；用户可见行为变化还必须更新用户手册。

## 2. 总体架构

代码采用 `src` 布局，依赖方向如下：

```text
bootstrap -> ui -> application -> domain
     |           |            |
     +---------->+------------+-> infrastructure implements domain ports
```

- `domain` 只依赖 Python 标准库，定义不可变模型、状态、错误、编解码、缓冲和外部能力协议。
- `application` 编排会话、Worker、日志和状态，不依赖 PySide6。
- `infrastructure` 实现 `Transport`、`PortScanner`、`ConfigStore`、`LogSink` 和 `Clock` 协议。
- `ui` 依赖 PySide6 与 application 控制器，通过不可变快照和记录更新界面。
- `bootstrap` 组装真实对象并启动 Qt 应用。

不能把串口 I/O、文件 I/O 或 Qt 类型放入 domain；也不能让 infrastructure 反向依赖 UI。

## 3. 关键公共模型与协议

### 3.1 `SerialConfig`

不可变串口配置，主要字段和默认值：

| 字段 | 默认值 | 约束 |
|---|---|---|
| `port` | 空字符串 | 未连接时可为空，连接前必须非空 |
| `baudrate` | `115200` | 正整数 |
| `bytesize` | `8` | `5`、`6`、`7`、`8` |
| `parity` | `N` | `N`、`E`、`O`、`M`、`S` |
| `stopbits` | `1.0` | `1`、`1.5`、`2` |
| `flow_control` | `none` | `none`、`xonxoff`、`rtscts`、`dsrdtr` |
| `dtr` / `rts` | `True` | 布尔值 |
| `encoding` | `utf-8` | `utf-8`、`gb18030`、`ascii` |

`validate()` 检查不依赖连接状态的字段；`validate_for_connect()` 额外要求端口非空。

### 3.2 记录与快照

- `LogRecord` 保存 UTC 时间、方向、原始 `bytes`、文本编码、文本、HEX 和会话 ID。
- `LogRecord.from_bytes()` 是创建串口记录的标准入口，文本和 HEX 必须从原始字节派生。
- `SessionSnapshot` 保存会话 ID、标题、状态、配置、最后错误、RX/TX 字节数和累计淘汰记录数。
- 回调跨线程传递时只使用不可变 `LogRecord` 和 `SessionSnapshot`。

### 3.3 外部能力协议

`domain/ports.py` 定义：

- `Transport`：打开/关闭、读取、完整写入、DTR/RTS 和打开状态。
- `PortScanner`：返回不可变端口名称元组。
- `Clock`：返回带时区 UTC 时间和单调时钟。
- `ConfigStore`：加载和保存应用配置。
- `LogSink`：打开、写入、刷新和关闭日志。

测试使用 Fake 实现替换这些协议，不依赖真实硬件。

## 4. 会话状态机

`SessionState` 的稳定值：

```text
disconnected -> connecting -> connected -> disconnecting -> disconnected
                      |                         |
                      +------> error <-----------+
```

`SessionStateMachine` 只允许以下显式转换：

- `connect()`：`disconnected/error -> connecting`
- `mark_connected()`：`connecting -> connected`
- `mark_connect_failed()`：`connecting -> error`
- `begin_disconnect()`：`connected -> disconnecting`
- `mark_disconnected()`：`disconnecting -> disconnected`
- `mark_cleanup_failed()`：`disconnecting -> error`
- `reset()`：`error -> disconnected`
- `close(force=False)`：`disconnected/error` 可关闭；活动状态必须显式 `force=True`

非法转换统一抛出 `InvalidStateTransitionError`，不得直接改写状态。

## 5. 线程、队列与并发边界

- Qt 主线程负责所有窗口和控件操作。
- 每个连接创建一个标准库 `threading.Thread`，名称为 `qserialtool-serial-worker`，不是 `QThread`。
- Worker 默认读取块大小为 `8192` 字节，读取超时 `50 ms`，关闭超时 `1 s`。
- 发送队列最大 `256` 个写入任务；队列满时抛出 `SendQueueFullError`，不阻塞 UI。
- DTR/RTS 使用无界的小型控制队列；队列元素是固定布尔控制命令，不存在用户数据堆积风险。
- `SessionController` 和 `SessionManager` 使用 `RLock` 保护共享状态。
- Worker 通过 `WorkerEventHandler` 回调 controller；UI 由 `QtSessionBridge` 把回调转换为 Qt 信号，并以 queued connection 投递到主线程。
- 控件不得读取 Worker 内部状态，只能读取 controller 的不可变快照或缓冲副本。

## 6. 关键数据流

### 6.1 连接

1. UI 从连接面板构造并验证 `SerialConfig`。
2. `SessionManager` 检查进程内是否已有其他活动会话占用同一端口。
3. `SessionController` 把状态切换为 `connecting`，创建并启动 `SerialWorker`。
4. Worker 创建 `SerialTransport`、调用 `open()`、应用 DTR/RTS。
5. 成功时 controller 进入 `connected`，关闭旧日志（若存在），并按偏好创建本次自动日志。
6. 失败时进入 `error`，发布用户可读错误快照，界面允许修改参数后重试。

### 6.2 接收

1. Worker 循环读取最多 `8192` 字节，单次超时 `50 ms`。
2. `on_bytes_received()` 创建方向为 `rx` 的 `LogRecord`。
3. controller 同时写入有界内存缓冲和活动日志。
4. 记录通过回调发布，`QtSessionBridge` 将事件投递到 UI。
5. 接收面板根据暂停、RX/TX 过滤和文本/HEX 模式决定是否显示。

### 6.3 发送

1. UI 将文本编码或解析 HEX，再追加所选 CR/LF。
2. controller 要求状态为 `connected`，把非空 `bytes` 放入 Worker 的固定大小写队列。
3. Worker 使用 `write_all()` 在写入超时内发送完整任务。
4. 成功后创建方向为 `tx` 的 `LogRecord`，进入和接收相同的缓冲、日志和 UI 数据流。

### 6.4 断开和退出

1. controller 状态切换到 `disconnecting`，Worker 设置停止事件并等待最多 `1.5 s`。
2. Worker 退出循环，关闭 `Transport`，最后触发 `on_stopped()`。
3. controller 刷新并关闭活动日志，然后把状态改回 `disconnected`。
4. 超时则进入 `error` 并记录“等待串口线程退出超时”。
5. 关闭标签或退出程序时使用 `force=True`；退出前 Qt 主线程会等待 Worker 清理。

## 7. 缓冲、配置与日志实现

### 7.1 内存缓冲

`RecordBuffer` 默认同时限制 `100,000` 条记录和 `32 MiB` 原始字节。超过任一限制时从最旧记录开始淘汰；单条记录超过总字节上限时抛出 `BufferCapacityError`。`clear()` 只删除当前记录，不重置累计淘汰数。`ReceivePanel` 只渲染最近 `2000` 条并把隐藏条数写成提示行，`QPlainTextEdit` 文档块上限固定为 `2002`，避免整表重插阻塞主线程。

### 7.2 配置持久化

`JsonConfigStore` 实现 schema version `1`：

- Windows：`%APPDATA%\QSerialTool\settings.json`
- Linux：`${XDG_CONFIG_HOME:-$HOME/.config}/QSerialTool/settings.json`
- 保存前先把现有文件复制为 `.bak`，再写入 `.tmp`，执行 `fsync()` 后用原子替换提交。
- atomically 替换失败时抛出 `ConfigIOError`。
- 读取到不可解析或不受支持的内容时，复制为 `settings.corrupt.<UTC时间>.json` 并返回 `None`。
- 单个无效会话会被跳过，其他有效会话继续加载。
- `MainWindow` 使用 `500 ms` 单次定时器合并保存请求，保存前用最近一次成功的 `AppConfig` 与当前快照比较，完全相同时跳过写盘，并在退出时同步保存。

### 7.3 自动日志

`LogService` 管理单个会话的连接期日志：

- 默认目录是 `~/Documents/QSerialTool/Logs`，可由用户覆盖。
- 连接成功时创建文件，断开时刷新并关闭。
- 文件名为 `QSerialTool_<清理后的端口>_YYYYMMDD_HHMMSS.<csv|txt>`；同名时追加数字后缀。
- 每累计 `256 KiB` 或经过 `1 s` 时刷新一次，具体取决于先达到的条件。
- 日志错误保存为会话错误，但不会中断串口 I/O。

CSV 输出使用 `utf-8-sig` 和 RFC 4180 字段：`timestamp`、`direction`、`encoding`、`text`、`hex`。TXT 使用 UTF-8，格式为 `[本地时间] 方向 [编码] 文本`。

## 8. UI 层职责

- `MainWindow`：单行头部，不创建 `QMenuBar` 与 `QToolBar`；标签栏右上角角落控件依次承载“主题”下拉框、“+”新建按钮和“☰”菜单（新建会话/关闭当前会话/退出），菜单动作额外用 `addAction()` 挂到窗口以保留 `Ctrl+T/W/Q`；负责标签、窗口状态与配置保存（内容未变化时跳过写盘），窗口最小尺寸 900×600，主题变化后对每个 `SessionTab` 调用 `refresh_theme()`。
- `SessionTab`：用水平 `QSplitter` 组合左侧设置面板和右侧收发区；设置面板是 `QScrollArea`，内容控件挂在 `sidebar_content` 上，接收标题行最左侧是侧栏折叠按钮，底部状态条由 `state_indicator` 色点和 `status_label` 组成。
- `ConnectionPanel`：端口刷新、配置校验、连接/断开和 DTR/RTS；表单标签右对齐，端口集合不变时不重建下拉框以保留输入光标；`set_refresh_active()` 按标签可见性启停轮询，自动枚举周期为 30 s，端口行右侧 `refresh_button` 可手动立即枚举（连接中与端口控件一同禁用）。
- `ReceivePanel`：接收标题行（格式、时间戳、方向过滤、暂停、清屏、自动滚动）和内存缓冲显示；输出控件使用 `theme_manager.data_font()` 等宽字体，取色走 `theme_manager.data_colors()`，可通过 `add_leading_header_widget()` 在标题行左侧插入外部控件，并通过 `refresh_theme()` 响应主题切换。
- `SendPanel`：两行标题（格式/换行/发送、历史/间隔/周期）、文本/HEX 编码和周期发送；编辑器使用等宽字体。
- `LogPanel`：以“日志与导出”分组呈现自动日志设置、打开目录和导出当前缓冲；长路径状态文本不参与最小宽度计算，并按标签宽度做中间省略，完整路径保留在 tooltip。
- `theme_manager`：`apply_theme()` 设置深色角色、占位符文字和深色禁用态文字颜色；`resolved_theme()`、`data_colors()` 和 `data_font()` 提供主题解析结果、数据区配色和等宽字体。
- `QtSessionBridge`：把 Worker 线程事件转换为 Qt 信号。

界面组件只通过 controller 的公共方法执行动作；跨线程 UI 更新必须经过 queued signal 或 Qt 定时器，禁止直接从 Worker 修改控件。

## 9. 错误模型

所有领域错误继承 `DomainError`，携带稳定 `ErrorCode`、用户消息、可恢复标志和建议。`SessionSnapshot.last_error` 使用不可变 `UserFacingError`。主要分类包括：

- 输入与 HEX/文本编码错误。
- 非法状态转换、缓冲容量和发送队列满。
- 端口不存在、占用、权限不足和传输 I/O 错误。
- 日志与配置文件 I/O 错误。
- 未预期内部错误。

底层 `pyserial` 异常在 `SerialTransport` 边界映射为领域错误；UI 不显示未处理的 traceback。

## 10. 质量门禁与文档同步

标准本地命令：

```powershell
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
```

启用提交前文档同步 Hook：

```powershell
git config core.hooksPath .githooks
```

手动检查模式：

```powershell
.\.venv\Scripts\python.exe scripts\check_docs_sync.py --staged
.\.venv\Scripts\python.exe scripts\check_docs_sync.py --base origin/main
.\.venv\Scripts\python.exe scripts\check_docs_sync.py --working-tree
```

规则位于 `docs/doc-sync-rules.json`。UI 变更必须至少同步用户手册或开发指南；domain/application 变更必须同步开发指南或 ADR；基础设施变更必须同步开发指南或用户手册；构建和项目元数据变更必须同步对应技术文档。未配置运行时路径会直接失败。

GitHub Actions 在 push 和 pull request 上执行同一检查、Ruff 和离屏 pytest。CI 用于防止 `--no-verify` 等本地绕过；本地 Hook 用于尽早反馈，但机器检查只能证明相关文档发生了变更，不能代替人工核对语义准确性。

## 11. 扩展清单

新增或修改功能时依次执行：

1. 阅读 `implementation-plan.md`、相关 ADR、源码、测试和用户手册。
2. 明确接口、状态转换、线程边界、错误和资源上限。
3. 先增加失败测试，再实现最小改动。
4. 同步更新 `developer-guide.md`；存在用户可见变化时更新 `user-guide.md`。
5. 涉及公共接口、数据格式、线程模型或发布方式时新增或更新 ADR。
6. 运行 Ruff、相关单测、集成测试和文档同步检查。
7. 打包或真实硬件相关变化按发布清单完成对应验收。
