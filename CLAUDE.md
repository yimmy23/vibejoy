# VibeJoy

将游戏手柄输入映射为 macOS 快捷键的本地工具；包管理器 uv。

- 输入轮询不能等待用户 shell 命令；已有 daemon 占用 HID 时通过 IPC 操作设备。
- 保留设备校准、按键释放及严格配置校验行为。
- 特殊验证：`uv run vibejoy validate`（配置）、`uv run vibejoy doctor`（设备/权限）；相关测试用 `uv run pytest <测试路径>`。

按需读取：[设备与架构](docs/agents/hardware.md)（输入/IPC/映射器）、[测试](docs/agents/testing.md)（行为验证）、[发布](docs/agents/release.md)（版本发布）。
