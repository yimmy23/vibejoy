# 测试

- mapper 测试使用项目现有 FakeKeyboard/FakeWindow 和 shell recorder，避免直接操作用户桌面。
- 保留真实 subprocess smoke，防止把真正的进程 API 错误模拟掉。
- 单元测试不能证明真实 HID/蓝牙/辅助功能权限；相关硬件变化用现有 discover、doctor 或设备探针验证。
- 只运行覆盖本次改动的测试；纯文档改动无需连接手柄。复用同版本可追溯的验证。
