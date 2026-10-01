# ADR-0001：Worker 线程和会话边界

- 状态：Accepted
- 日期：2026-10-01
- 决策范围：M2 串口链路

## 背景

QSerialTool 计划在 Windows 和 Linux 上运行，UI 使用 PySide6，串口由 pyserial 负责。串口读写可能阻塞，不能直接运行在 UI 主线程；同时多标签会话需要隔离状态、队列和资源生命周期。

## 候选方案

1. 在 Qt 主线程直接访问 pyserial：实现简单，但阻塞操作会造成界面卡死。
2. 使用 Qt `QThread` 并让应用层依赖 PySide6：与现有 UI 集成方便，但会破坏领域和应用层的框架无关性。
3. 使用 Python 标准库 `Thread`、`Event` 和 `Queue` 构建 Worker：框架无关、便于确定性测试，后续由 UI 适配层桥接信号。

## 决策

采用方案 3。

- 每个已连接会话对应一个 `SerialWorker` 和非守护线程。
- Worker 独占一个 `Transport` 实例，所有串口 I/O 只在该线程执行。
- Worker 使用有界发送队列（默认 256 项）接收写入，使用独立控制队列处理 DTR/RTS。
- Worker 通过 `WorkerEventHandler` 协议向 `SessionController` 发送不可变事件。
- `SessionController` 维护状态机、缓冲、统计和 Worker 生命周期，不依赖 PySide6。
- `SessionManager` 负责会话注册和同进程重复端口检查，不负责 UI 展示。
- UI 集成阶段通过 PySide6 信号桥接 Worker 回调，不把 Qt 类型下沉到应用层。

## 后果

优点：

- 串口 I/O 不阻塞 UI。
- 领域层、应用层不依赖 Qt，可独立单元测试。
- 每个标签的资源和状态边界明确。
- Windows 和 Linux 使用相同并发模型。

约束：

- 回调由 Worker 线程触发，Qt UI 必须通过线程安全信号桥接。
- Worker 必须在关闭时显式停止并等待，应用退出不能跳过清理。
- 发送队列必须有界，满队列必须返回明确错误。
- 线程无法安全强杀，打开或系统调用长时间阻塞时只能标记清理失败并报告。

## 验证

- 使用 Fake Transport 覆盖命令、读写、异常、停止和队列满路径。
- 使用 pyserial `loop://` 验证真实 Worker 线程中的收发链路。
- 全量测试时确保所有 Worker 均结束，不遗留非守护线程。