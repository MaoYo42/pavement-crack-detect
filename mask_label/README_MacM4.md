# 路面裂缝分割标注软件 (Mac M4 & macOS 26+ 定制版)

这是一个功能完善的图像标注工具，专为路面裂缝的分割标注设计。

**特别说明**：针对 Mac M4 芯片以及 macOS 26+ 系统中自带 Python 3.9 的 `Tkinter` (Tcl/Tk) 版本兼容性问题，本指南进行了专属环境配置的适配，请务必按照以下流程操作。


/Users/maoyo/Projects/auto_labeling_workspace/gui_venv/bin/python /Users/maoyo/Projects/auto_labeling_workspace/mask_label/crack_labeler.py


---

## 🚀 1. 环境配置 (首次运行必看)

由于较新的 macOS 系统对自带图形库存在极严格的限制，我们需要使用 Homebrew 提供的现代化 Python 版本来构建专属的 GUI 虚拟环境。

### 1.1 安装依赖环境 (终端执行)
如果您的电脑还没有配置这些前置依赖，请在终端（Terminal）中运行：
```bash
# 安装 Python 3.12 及其适配的 Tkinter 图形库
brew install python@3.12 python-tk@3.12
```

### 1.2 创建专属 GUI 虚拟环境
在工作区根目录下创建名为 `gui_venv` 的虚拟环境，并安装必要的绘图库：
```bash
# 切换到工作目录
cd /Users/maoyo/Projects/auto_labeling_workspace

# 创建基于 Homebrew Python 3.12 的虚拟环境
/opt/homebrew/bin/python3.12 -m venv gui_venv

# 激活环境并安装依赖
source gui_venv/bin/activate
pip install pillow opencv-python numpy
deactivate
```

---

## 🏃 2. 启动与运行

以后每次启动标注工具时，**请务必使用这个定制的 `gui_venv` 环境**，无需进入 `mask_label` 文件夹，直接在终端执行：

```bash
# 一键启动指令
/Users/maoyo/Projects/auto_labeling_workspace/gui_venv/bin/python /Users/maoyo/Projects/auto_labeling_workspace/mask_label/crack_labeler.py
```

```bash
/Users/maoyo/Projects/auto_labeling_workspace/gui_venv/bin/python /Users/maoyo/Projects/auto_labeling_workspace/mask_label/crack_labeler_3d.py
```



---

## 📦 3. 实战工作流 (针对当前项目)

在弹出的图形界面中，请按照以下步骤加载我们刚跑完自动标注的数据集：

1. **加载项目**：点击菜单栏 `文件` -> `加载项目文件夹`。
2. **选择路径**：选中我们精修过的数据集目录：
   `/Users/maoyo/Projects/auto_labeling_workspace/core_assets/V2_Polished`
3. **开始检阅**：程序会自动将 3305 张图片及其对应的红色 Mask 对齐加载。

---

## ⌨️ 4. 核心快捷键 (科研高效版)

*   **`A` / `D` (或 `←` / `→`)**：**极速翻页**。由于程序内置了自动保存机制，翻页时会自动保存您对上一张图的修改。
*   **长按 `S` 键**：**透视原图**。按下瞬时隐藏红色 Mask，松开恢复。这是最重要的功能，用于检查模型是否正确贴合了实际裂缝的边缘。
*   **`W` 键**：**工具切换**。在“画笔（补充漏检区域）”和“橡皮擦（擦除多余噪点/白标线干扰）”之间无缝切换。
*   **`Command + Z`**：撤销（支持多达 50 步）。
*   **鼠标滚轮/触控板双指**：以鼠标指针为中心，支持高达 10x 的无损缩放。

---

## 💡 5. 常见问题排查策略

*   **报错 `macOS 26 (2603) or later required...`**
    *   **原因**：使用了系统自带的 `python` 或旧的虚拟环境启动。
    *   **解决**：请确认启动指令使用的是 `/Users/maoyo/.../gui_venv/bin/python`。
*   **报错 `ModuleNotFoundError: No module named '_tkinter'`**
    *   **原因**：Python 没有绑定正确的图形支持。
    *   **解决**：运行 `brew install python-tk@3.12` 后重建虚拟环境。
*   **发现 Mask 有轻微的锯齿？**
    *   不用在工具里手动一点点擦，退出工具，跑一下我们的 `tool_2_mask_refiner.py` 进行自动化形态学“磨皮”，再重新加载。
