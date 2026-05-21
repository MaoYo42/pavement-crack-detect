# Pavement Crack Detect — 路面裂缝智能检测分割系统

**BSc Computer Science Thesis Project** @ Southwest Forestry University

基于 U-Net (ResNet34) + FastAPI 的路面裂缝检测与分割平台。包含完整的数据标注工具、模型训练/评估流水线和 Web 推理系统。

---

## 📦 仓库结构

```
├── app/                    ← Windows 版推理系统 (FastAPI)
├── app_macos/              ← macOS 版推理系统 (FastAPI + Glassmorphism UI)
├── mask_label/             ← 路面裂缝标注工具 (Tkinter GUI)
├── CRACK745/               ← 自标注裂缝分割数据集 (596 train + 149 val)
├── val/                    ← 演示用测试集 (与 CRACK745/val 同步)
└── requirements.txt
```

## 🧰 三模块概览

### 1️⃣ 标注工具 — `mask_label/`

Tkinter 桌面 GUI 标注工具，支持：

- **画笔/橡皮擦**：在 mask 上绘制/擦除裂缝区域
- **滚轮缩放**：以鼠标为中心 0.1x–10x 缩放
- **S 键预览**：按住显示原图，松开恢复 mask 叠加
- **批量标注**：加载整个文件夹，A/D 键翻页，自动保存
- **50 步撤回**：`⌘Z` / `Ctrl+Z`

```bash
cd mask_label && pip install -r requirements.txt
python crack_labeler.py
```

### 2️⃣ CRACK745 数据集

745 张路面裂缝图像 + 对应像素级标注 mask：

| 集 | 数量 | 说明 |
|------|------|------|
| train | 596 + 596 | 训练集 (图像 + mask) |
| val | 149 + 149 | 验证/测试集 |

像素值：白色(255)=裂缝，黑色(0)=背景。PNG 无损格式。

### 3️⃣ 推理系统 — `app/` & `app_macos/`

| 功能 | 说明 |
|------|------|
| 引擎 | U-Net (ResNet34 encoder) |
| 推理设备 | CUDA / MPS / CPU 自动选择 |
| 前端 | Glassmorphism 暗调 UI，原生 HTML/CSS/JS |
| 鉴权 | JWT 双角色 (user/admin) |
| 存储 | SQLite (任务记录、结果、日志) |

```bash
# macOS
cd app_macos && pip install -r ../requirements.txt
python -m uvicorn app_macos.main:app --host 0.0.0.0 --port 8000

# Windows
start.bat
```

## 🧪 其他模型权重 (app/models/)

| 文件 | 说明 |
|------|------|
| `best.pt` | YOLOv11-seg 训练权重 |
| `v11s_100_8_best.pt` | YOLOv11s-seg 训练权重 |
| `yolov11_seg_best.pt` | YOLOv11-seg 参考权重 |
| `yolov12_seg_best.pt` | YOLOv12-seg 参考权重 |

*主推理模型权重 (~93MB) 未入库，需单独获取。*

## 📄 许可

西南林业大学 · 计算机科学本科毕业论文项目
