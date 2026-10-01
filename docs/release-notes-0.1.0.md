# QSerialTool 0.1.0 发布说明

## 状态

发布候选，待完成 Windows/Linux 真实硬件和干净环境验收。

## 功能

- Windows/Linux 跨平台桌面界面。
- 多标签串口会话。
- 端口热插拔扫描。
- 常见及自定义串口参数。
- DTR/RTS 控制。
- 文本和 HEX 收发。
- UTF-8、GB18030、ASCII 编码。
- 时间戳、RX/TX 分色、过滤、暂停和清屏。
- 发送历史和周期发送。
- CSV/TXT 自动日志和手动导出。
- 会话配置恢复。
- 系统/浅色/深色主题。

## 已知限制

- 尚未完成真实串口硬件验收。
- 当前仅实际执行了 Windows 单文件构建；Linux 构建需在 Linux 环境验证。
- 当前机器 Application Control 策略阻止直接运行本地生成的 `QSerialTool.exe`。
- 不包含文件发送、Modbus 解析、脚本、日志回放和协议插件。
- 无代码签名、自动更新和遥测。