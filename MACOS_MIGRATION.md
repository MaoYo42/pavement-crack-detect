# macOS 版本说明

这是一个与原 Windows 版本并行的 macOS 专用实现，入口为 `app_macos.main:app`。

## 变化点

- 数据库默认迁移到 `~/Library/Application Support/Interface/crack_detection_macos.db`
- 输出目录默认迁移到 `~/Library/Application Support/Interface/outputs`
- 模型权重支持 `MODEL_PATH` 环境变量覆盖
- 批处理目录不再使用 Windows 反斜杠
- 路径输入支持 macOS 原生 POSIX 路径
- mask 文件使用 PIL 保存，避免 OpenCV 在跨平台路径上的兼容风险

## 启动

可以直接双击 `start_macos.command`，或在终端执行：

```bash
python3 -m uvicorn app_macos.main:app --reload --host 0.0.0.0 --port 8000
```

## 可配置项

- `INTERFACE_MACOS_RUNTIME_DIR`
- `INTERFACE_MACOS_OUTPUT_DIR`
- `MODEL_PATH`
- `ALLOW_ORIGINS`
- `MAX_UPLOAD_MB`

