#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路面裂缝分割标注软件
主要功能：加载图像和mask，使用画笔和橡皮擦工具编辑mask
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import cv2
import numpy as np
from PIL import Image, ImageTk
import os


class CrackLabeler:
    def __init__(self, root):
        self.root = root
        self.root.title("路面裂缝标注工具")

        # 图像相关变量
        self.image = None
        self.mask = None
        self.display_image = None
        self.image_path = None
        self.mask_path = None

        # 文件夹批量处理相关变量
        self.image_folder = None
        self.mask_folder = None
        self.image_files = []
        self.current_index = 0

        # 撤回功能相关变量
        self.undo_stack = []
        self.max_undo_steps = 50

        # mask显示相关变量
        self.saved_alpha = 0.5  # 保存的透明度值
        self.is_mask_hidden = False  # 防止S键长按重复触发

        # 分类移动相关变量
        self.categories = {
            'repaired': {'folder': None, 'count': 0, 'desc': '修补', 'prefix': '[R]修补', 'color': 'orange'},
            'true_crack': {'folder': None, 'count': 0, 'desc': '真裂缝', 'prefix': '[T]真裂缝', 'color': 'green'},
            'false_crack': {'folder': None, 'count': 0, 'desc': '伪裂缝', 'prefix': '[F]伪裂缝', 'color': 'red'}
        }
        self.category_labels = {}

        # 画笔相关变量
        self.brush_size = 10
        self.current_tool = "brush"  # brush 或 eraser
        self.drawing = False
        self.last_x = None
        self.last_y = None

        # 显示相关变量
        self.canvas_width = 1200
        self.canvas_height = 800
        self.zoom_factor = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.is_panning = False

        self.setup_ui()
        self.setup_shortcuts()

    def setup_ui(self):
        """设置用户界面"""
        # 创建菜单栏
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="加载图像", command=self.load_image)
        file_menu.add_command(label="加载Mask", command=self.load_mask)
        file_menu.add_separator()
        file_menu.add_command(label="加载图像文件夹", command=self.load_image_folder)
        file_menu.add_command(label="加载Mask文件夹", command=self.load_mask_folder)
        file_menu.add_separator()
        file_menu.add_command(label="加载项目文件夹", command=self.load_project_folder)
        file_menu.add_separator()
        file_menu.add_command(label="保存Mask", command=self.save_mask)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)

        # 创建帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="快捷键说明", command=self.show_shortcuts_help)

        # 创建工具栏
        toolbar = tk.Frame(self.root, relief=tk.RAISED, borderwidth=2)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        # 工具选择
        tk.Label(toolbar, text="工具:").pack(side=tk.LEFT, padx=5)
        self.tool_var = tk.StringVar(value="brush")
        brush_btn = tk.Radiobutton(toolbar, text="画笔", variable=self.tool_var,
                                   value="brush", command=self.change_tool)
        brush_btn.pack(side=tk.LEFT, padx=5)
        eraser_btn = tk.Radiobutton(toolbar, text="橡皮擦", variable=self.tool_var,
                                    value="eraser", command=self.change_tool)
        eraser_btn.pack(side=tk.LEFT, padx=5)

        # 画笔大小
        tk.Label(toolbar, text="画笔大小:").pack(side=tk.LEFT, padx=10)
        self.size_var = tk.IntVar(value=10)
        size_scale = tk.Scale(toolbar, from_=1, to=20, orient=tk.HORIZONTAL,
                             variable=self.size_var, command=self.change_brush_size)
        size_scale.pack(side=tk.LEFT, padx=5)
        self.size_label = tk.Label(toolbar, text="10")
        self.size_label.pack(side=tk.LEFT, padx=5)

        # Mask透明度
        tk.Label(toolbar, text="Mask透明度:").pack(side=tk.LEFT, padx=10)
        self.alpha_var = tk.DoubleVar(value=0.5)
        alpha_scale = tk.Scale(toolbar, from_=0, to=1, resolution=0.1, orient=tk.HORIZONTAL,
                              variable=self.alpha_var, command=self.update_display)
        alpha_scale.pack(side=tk.LEFT, padx=5)

        # 导航按钮
        tk.Label(toolbar, text=" | ").pack(side=tk.LEFT, padx=5)
        self.prev_btn = tk.Button(toolbar, text="上一张", command=self.prev_image, state=tk.DISABLED)
        self.prev_btn.pack(side=tk.LEFT, padx=5)
        self.next_btn = tk.Button(toolbar, text="下一张", command=self.next_image, state=tk.DISABLED)
        self.next_btn.pack(side=tk.LEFT, padx=5)
        self.file_info_label = tk.Label(toolbar, text="")
        self.file_info_label.pack(side=tk.LEFT, padx=10)

        # 分类移动信息
        tk.Label(toolbar, text=" | ").pack(side=tk.LEFT, padx=5)
        for cat_key, cat_info in self.categories.items():
            lbl = tk.Label(toolbar, text=f"{cat_info['prefix']}:0", fg=cat_info['color'])
            lbl.pack(side=tk.LEFT, padx=5)
            self.category_labels[cat_key] = lbl

        # 创建画布
        canvas_frame = tk.Frame(self.root)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.canvas = tk.Canvas(canvas_frame, width=self.canvas_width,
                               height=self.canvas_height, bg='gray')
        self.canvas.pack()

        # 绑定鼠标事件
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        # 绑定鼠标滚轮缩放
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)  # Windows/Mac
        self.canvas.bind("<Button-4>", self.on_mouse_wheel)    # Linux 向上滚动
        self.canvas.bind("<Button-5>", self.on_mouse_wheel)    # Linux 向下滚动

        # 状态栏
        self.status_bar = tk.Label(self.root, text="就绪", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def setup_shortcuts(self):
        """设置快捷键"""
        # 撤回：Command+Z (Mac) 或 Ctrl+Z (Windows/Linux)
        self.root.bind("<Command-z>", lambda e: self.undo())
        self.root.bind("<Control-z>", lambda e: self.undo())

        # 上一张：左箭头或上箭头或A键
        self.root.bind("<Left>", lambda e: self.prev_image())
        self.root.bind("<Up>", lambda e: self.prev_image())
        self.root.bind("a", lambda e: self.prev_image())
        self.root.bind("A", lambda e: self.prev_image())

        # 下一张：右箭头或下箭头或D键
        self.root.bind("<Right>", lambda e: self.next_image())
        self.root.bind("<Down>", lambda e: self.next_image())
        self.root.bind("d", lambda e: self.next_image())
        self.root.bind("D", lambda e: self.next_image())

        # 切换工具：W键
        self.root.bind("w", lambda e: self.toggle_tool())
        self.root.bind("W", lambda e: self.toggle_tool())

        # S键：按下隐藏mask，放开显示mask
        self.root.bind("<KeyPress-s>", lambda e: self.hide_mask())
        self.root.bind("<KeyPress-S>", lambda e: self.hide_mask())
        self.root.bind("<KeyRelease-s>", lambda e: self.show_mask())
        self.root.bind("<KeyRelease-S>", lambda e: self.show_mask())

        # 删除当前图像：Delete 或 Backspace
        self.root.bind("<Delete>", lambda e: self.delete_current_image())
        self.root.bind("<BackSpace>", lambda e: self.delete_current_image())

        # 标记分类快捷键
        self.root.bind("r", lambda e: self.move_to_category('repaired'))
        self.root.bind("R", lambda e: self.move_to_category('repaired'))
        self.root.bind("t", lambda e: self.move_to_category('true_crack'))
        self.root.bind("T", lambda e: self.move_to_category('true_crack'))
        self.root.bind("f", lambda e: self.move_to_category('false_crack'))
        self.root.bind("F", lambda e: self.move_to_category('false_crack'))

    def load_image(self):
        """加载图像"""
        file_path = filedialog.askopenfilename(
            title="选择图像文件",
            filetypes=[("图像文件", "*.jpg *.jpeg *.png *.bmp"), ("所有文件", "*.*")]
        )
        if file_path:
            self.image_path = file_path
            self.image = cv2.imread(file_path)
            if self.image is None:
                messagebox.showerror("错误", "无法加载图像")
                return
            self.image = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)

            # 如果没有mask，创建空白mask
            if self.mask is None:
                self.mask = np.zeros(self.image.shape[:2], dtype=np.uint8)

            self.update_display()
            self.status_bar.config(text=f"已加载图像: {os.path.basename(file_path)}")

    def load_mask(self):
        """加载mask标签"""
        file_path = filedialog.askopenfilename(
            title="选择Mask文件",
            filetypes=[("图像文件", "*.jpg *.jpeg *.png *.bmp"), ("所有文件", "*.*")]
        )
        if file_path:
            self.mask_path = file_path
            mask = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
            if mask is None:
                messagebox.showerror("错误", "无法加载Mask")
                return

            # 如果有图像，确保mask尺寸匹配
            if self.image is not None:
                if mask.shape != self.image.shape[:2]:
                    mask = cv2.resize(mask, (self.image.shape[1], self.image.shape[0]))

            self.mask = mask
            self.update_display()
            self.status_bar.config(text=f"已加载Mask: {os.path.basename(file_path)}")

    def load_image_folder(self):
        """加载图像文件夹"""
        folder_path = filedialog.askdirectory(title="选择图像文件夹")
        if folder_path:
            self.image_folder = folder_path
            # 获取所有图像文件
            self.image_files = []
            for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.JPG', '*.JPEG', '*.PNG', '*.BMP']:
                self.image_files.extend(sorted([f for f in os.listdir(folder_path)
                                               if f.lower().endswith(ext[1:])]))

            if not self.image_files:
                messagebox.showwarning("警告", "文件夹中没有找到图像文件")
                self.root.focus_force()  # 恢复焦点
                return

            self.current_index = 0
            self.load_image_by_index(self.current_index)
            self.update_navigation_buttons()
            self.status_bar.config(text=f"已加载图像文件夹: {folder_path} (共{len(self.image_files)}张)")
        else:
            self.root.focus_force()  # 恢复焦点

    def load_mask_folder(self):
        """加载mask文件夹"""
        folder_path = filedialog.askdirectory(title="选择Mask文件夹")
        if folder_path:
            self.mask_folder = folder_path
            # 如果已经加载了图像，尝试加载对应的mask
            if self.image_files and self.current_index < len(self.image_files):
                self.load_mask_by_index(self.current_index)
            self.status_bar.config(text=f"已设置Mask文件夹: {folder_path}")
            self.root.focus_force()  # 恢复焦点
        else:
            self.root.focus_force()  # 恢复焦点

    def load_project_folder(self):
        """加载项目文件夹（包含images和masks子目录）"""
        folder_path = filedialog.askdirectory(title="选择项目文件夹（包含images和masks子目录）")
        if not folder_path:
            self.root.focus_force()  # 恢复焦点
            return

        # 检查images和masks子目录是否存在
        images_path = os.path.join(folder_path, "images")
        masks_path = os.path.join(folder_path, "masks")

        if not os.path.exists(images_path):
            messagebox.showerror("错误", f"未找到images子目录：{images_path}")
            self.root.focus_force()  # 恢复焦点
            return

        if not os.path.exists(masks_path):
            result = messagebox.askyesno("提示",
                f"未找到masks子目录：{masks_path}\n是否创建该目录？")
            if result:
                os.makedirs(masks_path)
            else:
                self.root.focus_force()  # 恢复焦点
                return

        # 设置图像和mask文件夹
        self.image_folder = images_path
        self.mask_folder = masks_path

        # 获取所有图像文件
        self.image_files = []
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.JPG', '*.JPEG', '*.PNG', '*.BMP']:
            self.image_files.extend(sorted([f for f in os.listdir(images_path)
                                           if f.lower().endswith(ext[1:])]))

        if not self.image_files:
            messagebox.showwarning("警告", "images文件夹中没有找到图像文件")
            self.root.focus_force()  # 恢复焦点
            return

        # 初始化修补等分类目标文件夹（项目文件夹同级 + _类别）
        parent_dir = os.path.dirname(folder_path)
        base_name = os.path.basename(folder_path)
        for cat_key, cat_info in self.categories.items():
            cat_info['folder'] = os.path.join(parent_dir, f"{base_name}_{cat_key}")
            cat_info['count'] = 0
            self.category_labels[cat_key].config(text=f"{cat_info['prefix']}:0")

        self.current_index = 0
        self.load_image_by_index(self.current_index)
        self.update_navigation_buttons()
        self.status_bar.config(text=f"已加载项目: {folder_path} (共{len(self.image_files)}张)")

    def show_shortcuts_help(self):
        """显示快捷键帮助对话框"""
        help_window = tk.Toplevel(self.root)
        help_window.title("快捷键说明")
        help_window.geometry("600x500")
        help_window.resizable(False, False)

        # 创建滚动文本框
        text_frame = tk.Frame(help_window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        text_widget = tk.Text(text_frame, wrap=tk.WORD, yscrollcommand=scrollbar.set,
                             font=("Arial", 12), padx=10, pady=10)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)

        # 快捷键说明内容
        help_text = """快捷键说明

【导航控制】
A / ← / ↑        上一张图像
D / → / ↓        下一张图像
Delete / Backspace    删除当前图像和mask

【工具控制】
W               切换画笔/橡皮擦工具
S（按住）         临时隐藏mask（透明度变为0）
S（放开）         恢复mask显示

【编辑控制】
Command+Z (Mac)     撤回操作（最多50步）
Ctrl+Z (Win/Linux)  撤回操作（最多50步）

【鼠标操作】
左键拖动          使用当前工具绘制或擦除
滚轮向上          放大图像（1.1倍）
滚轮向下          缩小图像（0.9倍）
触控板双指缩放     平滑缩放图像

【使用技巧】
1. 粗标注：使用较大画笔（10-20像素）快速标注
2. 精细标注：滚轮放大后使用小画笔（1-5像素）
3. 查看原图：按住S键临时隐藏mask确认位置
4. 快速切换：使用A/D键快速浏览图像
5. 自动保存：切换图像时自动保存当前mask

【文件操作】
- 支持格式：JPG, JPEG, PNG, BMP
- Mask格式：PNG（推荐）
- 自动匹配：mask文件名与图像同名
"""

        text_widget.insert("1.0", help_text)
        text_widget.config(state=tk.DISABLED)  # 设置为只读

        # 关闭按钮
        close_btn = tk.Button(help_window, text="关闭", command=help_window.destroy,
                             font=("Arial", 12), padx=20, pady=5)
        close_btn.pack(pady=10)

    def load_image_by_index(self, index):
        """根据索引加载图像"""
        if index < 0 or index >= len(self.image_files):
            return

        file_name = self.image_files[index]
        file_path = os.path.join(self.image_folder, file_name)

        self.image_path = file_path
        self.image = cv2.imread(file_path)
        if self.image is None:
            messagebox.showerror("错误", f"无法加载图像: {file_name}")
            self.root.focus_force()  # 恢复焦点
            return
        self.image = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)

        # 清空撤回栈和重置缩放
        self.undo_stack = []
        self.zoom_factor = 1.0
        self.offset_x = 0
        self.offset_y = 0

        # 尝试加载对应的mask
        if self.mask_folder:
            self.load_mask_by_index(index)
        else:
            # 创建空白mask
            self.mask = np.zeros(self.image.shape[:2], dtype=np.uint8)

        self.update_display()
        self.file_info_label.config(text=f"{index + 1}/{len(self.image_files)}")
        self.status_bar.config(text=f"已加载: {file_name}")

        # 恢复焦点到主窗口，确保快捷键可用
        self.root.focus_force()

    def load_mask_by_index(self, index):
        """根据索引加载mask"""
        if not self.mask_folder or index >= len(self.image_files):
            return

        # 获取图像文件名（不含扩展名）
        image_name = self.image_files[index]
        base_name = os.path.splitext(image_name)[0]

        # 尝试多种可能的mask文件名
        mask_found = False
        for ext in ['.png', '.jpg', '.jpeg', '.bmp', '.PNG', '.JPG', '.JPEG', '.BMP']:
            mask_path = os.path.join(self.mask_folder, base_name + ext)
            if os.path.exists(mask_path):
                mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
                if mask is not None:
                    # 确保mask尺寸匹配
                    if self.image is not None and mask.shape != self.image.shape[:2]:
                        mask = cv2.resize(mask, (self.image.shape[1], self.image.shape[0]))
                    self.mask = mask
                    self.mask_path = mask_path
                    mask_found = True
                    break

        if not mask_found:
            # 如果没找到对应的mask，创建空白mask
            if self.image is not None:
                self.mask = np.zeros(self.image.shape[:2], dtype=np.uint8)

    def prev_image(self):
        """加载上一张图像"""
        if self.current_index > 0:
            # 自动保存当前mask
            if self.mask is not None and self.mask_folder:
                self.auto_save_mask()

            self.current_index -= 1
            self.load_image_by_index(self.current_index)
            self.update_navigation_buttons()

    def next_image(self):
        """加载下一张图像"""
        if self.current_index < len(self.image_files) - 1:
            # 自动保存当前mask
            if self.mask is not None and self.mask_folder:
                self.auto_save_mask()

            self.current_index += 1
            self.load_image_by_index(self.current_index)
            self.update_navigation_buttons()

    def delete_current_image(self):
        """删除当前图像和对应的mask"""
        if not self.image_files or self.current_index >= len(self.image_files):
            messagebox.showwarning("警告", "没有可删除的图像")
            self.root.focus_force()  # 恢复焦点
            return

        # 确认删除
        image_name = self.image_files[self.current_index]
        result = messagebox.askyesno("确认删除",
                                     f"确定要删除图像 '{image_name}' 吗？\n这将同时删除对应的mask文件（如果存在）。")
        if not result:
            self.root.focus_force()  # 恢复焦点
            return

        # 删除图像文件
        image_path = os.path.join(self.image_folder, image_name)
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as e:
            messagebox.showerror("错误", f"删除图像失败: {str(e)}")
            self.root.focus_force()  # 恢复焦点
            return

        # 删除对应的mask文件
        if self.mask_folder:
            base_name = os.path.splitext(image_name)[0]
            for ext in ['.png', '.jpg', '.jpeg', '.bmp', '.PNG', '.JPG', '.JPEG', '.BMP']:
                mask_path = os.path.join(self.mask_folder, base_name + ext)
                if os.path.exists(mask_path):
                    try:
                        os.remove(mask_path)
                    except Exception as e:
                        print(f"删除mask失败: {str(e)}")

        # 从列表中移除
        self.image_files.pop(self.current_index)

        # 加载下一张或上一张图像
        if len(self.image_files) == 0:
            # 没有图像了
            self.image = None
            self.mask = None
            self.canvas.delete("all")
            self.file_info_label.config(text="")
            self.status_bar.config(text="所有图像已删除")
            self.update_navigation_buttons()
            self.root.focus_force()  # 恢复焦点
        else:
            # 调整索引
            if self.current_index >= len(self.image_files):
                self.current_index = len(self.image_files) - 1
            self.load_image_by_index(self.current_index)
            self.update_navigation_buttons()
            self.status_bar.config(text=f"已删除: {image_name}")
            # load_image_by_index 已经会恢复焦点

    def update_navigation_buttons(self):
        """更新导航按钮状态"""
        if len(self.image_files) > 0:
            self.prev_btn.config(state=tk.NORMAL if self.current_index > 0 else tk.DISABLED)
            self.next_btn.config(state=tk.NORMAL if self.current_index < len(self.image_files) - 1 else tk.DISABLED)
        else:
            self.prev_btn.config(state=tk.DISABLED)
            self.next_btn.config(state=tk.DISABLED)

    def auto_save_mask(self):
        """自动保存mask到mask文件夹"""
        if self.mask is None or not self.mask_folder:
            return

        # 获取当前图像文件名
        image_name = self.image_files[self.current_index]
        base_name = os.path.splitext(image_name)[0]

        # 保存为PNG格式
        mask_path = os.path.join(self.mask_folder, base_name + '.png')
        cv2.imwrite(mask_path, self.mask)

    def save_mask(self):
        """保存mask"""
        if self.mask is None:
            messagebox.showwarning("警告", "没有可保存的Mask")
            return

        # 如果在批量模式下，自动保存到mask文件夹
        if self.mask_folder and self.image_files:
            self.auto_save_mask()
            messagebox.showinfo("成功", "Mask已保存到Mask文件夹")
            return

        # 否则弹出保存对话框
        file_path = filedialog.asksaveasfilename(
            title="保存Mask",
            defaultextension=".png",
            filetypes=[("PNG文件", "*.png"), ("所有文件", "*.*")]
        )
        if file_path:
            cv2.imwrite(file_path, self.mask)
            self.status_bar.config(text=f"已保存Mask: {os.path.basename(file_path)}")
            messagebox.showinfo("成功", "Mask已保存")

    def change_tool(self):
        """切换工具"""
        self.current_tool = self.tool_var.get()
        tool_name = "画笔" if self.current_tool == "brush" else "橡皮擦"
        self.status_bar.config(text=f"当前工具: {tool_name}")

    def toggle_tool(self):
        """切换画笔和橡皮擦工具"""
        if self.current_tool == "brush":
            self.tool_var.set("eraser")
            self.current_tool = "eraser"
            tool_name = "橡皮擦"
        else:
            self.tool_var.set("brush")
            self.current_tool = "brush"
            tool_name = "画笔"
        self.status_bar.config(text=f"当前工具: {tool_name}")

    def hide_mask(self):
        """隐藏mask（按下S键时）"""
        if self.is_mask_hidden:
            return  # 防止按键重复覆盖 saved_alpha
        self.is_mask_hidden = True
        self.saved_alpha = self.alpha_var.get()
        self.alpha_var.set(0)
        self.update_display()

    def show_mask(self):
        """显示mask（放开S键时）"""
        self.is_mask_hidden = False
        self.alpha_var.set(self.saved_alpha)
        self.update_display()

    def move_to_category(self, category_key):
        """将当前图像和mask标记为指定类别，并移动到独立文件夹"""
        if not self.image_files or self.current_index >= len(self.image_files):
            return

        cat_info = self.categories[category_key]

        if not cat_info['folder']:
            # 未通过项目文件夹加载时，用 image_folder 来推断
            if self.image_folder:
                parent_dir = os.path.dirname(self.image_folder)
                base_name = os.path.basename(os.path.dirname(self.image_folder)) if self.mask_folder else os.path.basename(self.image_folder)
                cat_info['folder'] = os.path.join(parent_dir, f"{base_name}_{category_key}")
            else:
                self.status_bar.config(text="请先加载项目文件夹")
                return

        # 创建分类目录
        target_img_dir = os.path.join(cat_info['folder'], "images")
        target_mask_dir = os.path.join(cat_info['folder'], "masks")
        os.makedirs(target_img_dir, exist_ok=True)
        os.makedirs(target_mask_dir, exist_ok=True)

        import shutil
        image_name = self.image_files[self.current_index]
        base_name_no_ext = os.path.splitext(image_name)[0]

        # 移动原图
        src_img = os.path.join(self.image_folder, image_name)
        if os.path.exists(src_img):
            shutil.move(src_img, os.path.join(target_img_dir, image_name))

        # 移动对应 mask
        if self.mask_folder:
            for ext in ['.png', '.jpg', '.jpeg', '.bmp']:
                mask_path = os.path.join(self.mask_folder, base_name_no_ext + ext)
                if os.path.exists(mask_path):
                    shutil.move(mask_path, os.path.join(target_mask_dir, base_name_no_ext + ext))
                    break

        # 更新计数和列表
        cat_info['count'] += 1
        self.category_labels[category_key].config(text=f"{cat_info['prefix']}:{cat_info['count']}")

        # 从文件列表中移除
        self.image_files.pop(self.current_index)

        # 加载下一张
        if len(self.image_files) == 0:
            self.image = None
            self.mask = None
            self.canvas.delete("all")
            self.file_info_label.config(text="")
            self.status_bar.config(text="所有图像已处理完毕")
            self.update_navigation_buttons()
            self.root.focus_force()
        else:
            if self.current_index >= len(self.image_files):
                self.current_index = len(self.image_files) - 1
            self.load_image_by_index(self.current_index)
            self.update_navigation_buttons()
            self.status_bar.config(text=f"已分类作 {cat_info['desc']}: {image_name} (剩余{len(self.image_files)}张)")

    def change_brush_size(self, value):
        """改变画笔大小"""
        self.brush_size = int(float(value))
        self.size_label.config(text=str(self.brush_size))

    def save_undo_state(self):
        """保存当前mask状态到撤回栈"""
        if self.mask is not None:
            # 保存mask的副本
            self.undo_stack.append(self.mask.copy())
            # 限制撤回栈大小
            if len(self.undo_stack) > self.max_undo_steps:
                self.undo_stack.pop(0)

    def undo(self):
        """撤回上一步操作"""
        if len(self.undo_stack) > 0:
            # 恢复上一个状态
            self.mask = self.undo_stack.pop()
            self.update_display()
            self.status_bar.config(text=f"已撤回 (剩余{len(self.undo_stack)}步可撤回)")
        else:
            self.status_bar.config(text="没有可撤回的操作")

    def on_mouse_down(self, event):
        """鼠标按下事件"""
        if self.image is None or self.mask is None:
            return

        # 保存当前mask状态到撤回栈
        self.save_undo_state()

        self.drawing = True
        self.last_x = event.x
        self.last_y = event.y
        self.draw_on_mask(event.x, event.y)

    def on_mouse_drag(self, event):
        """鼠标拖动事件"""
        if not self.drawing or self.image is None or self.mask is None:
            return

        # 从上一个点到当前点画线
        if self.last_x is not None and self.last_y is not None:
            self.draw_line_on_mask(self.last_x, self.last_y, event.x, event.y)

        self.last_x = event.x
        self.last_y = event.y

    def on_mouse_up(self, event):
        """鼠标释放事件"""
        self.drawing = False
        self.last_x = None
        self.last_y = None

    def draw_on_mask(self, canvas_x, canvas_y):
        """在mask上绘制"""
        if self.image is None or self.mask is None:
            return

        # 将画布坐标转换为图像坐标
        img_x, img_y = self.canvas_to_image_coords(canvas_x, canvas_y)

        if img_x < 0 or img_y < 0 or img_x >= self.mask.shape[1] or img_y >= self.mask.shape[0]:
            return

        # 根据工具类型设置颜色
        color = 255 if self.current_tool == "brush" else 0

        # 在mask上画圆
        cv2.circle(self.mask, (img_x, img_y), self.brush_size, color, -1)

        # 更新显示
        self.update_display()

    def draw_line_on_mask(self, x1, y1, x2, y2):
        """在mask上画线（连接两点）"""
        if self.image is None or self.mask is None:
            return

        # 将画布坐标转换为图像坐标
        img_x1, img_y1 = self.canvas_to_image_coords(x1, y1)
        img_x2, img_y2 = self.canvas_to_image_coords(x2, y2)

        # 根据工具类型设置颜色
        color = 255 if self.current_tool == "brush" else 0

        # 在mask上画线
        cv2.line(self.mask, (img_x1, img_y1), (img_x2, img_y2), color, self.brush_size * 2)

        # 更新显示
        self.update_display()

    def canvas_to_image_coords(self, canvas_x, canvas_y):
        """将画布坐标转换为图像坐标"""
        if self.display_image is None or self.image is None:
            return 0, 0

        # 获取显示图像的尺寸
        display_h, display_w = self.display_image.shape[:2]

        # 计算图像在画布上的位置（考虑缩放和偏移）
        x_offset = (self.canvas_width - display_w) // 2 + self.offset_x
        y_offset = (self.canvas_height - display_h) // 2 + self.offset_y

        # 转换为显示图像坐标
        display_x = canvas_x - x_offset
        display_y = canvas_y - y_offset

        # 计算缩放比例
        scale_x = self.image.shape[1] / display_w
        scale_y = self.image.shape[0] / display_h

        # 转换为原始图像坐标
        img_x = int(display_x * scale_x)
        img_y = int(display_y * scale_y)

        return img_x, img_y

    def on_mouse_wheel(self, event):
        """鼠标滚轮和触控板缩放"""
        if self.image is None:
            return

        # 获取鼠标位置
        mouse_x = event.x
        mouse_y = event.y

        # 确定缩放方向和比例
        # Mac触控板会产生较小的delta值，鼠标滚轮产生较大的delta值
        if hasattr(event, 'delta'):
            if event.delta > 0:  # 向上滚动或双指放大
                scale = 1.1 if abs(event.delta) > 50 else 1.0 + abs(event.delta) / 1000
            elif event.delta < 0:  # 向下滚动或双指缩小
                scale = 0.9 if abs(event.delta) > 50 else 1.0 - abs(event.delta) / 1000
            else:
                return
        elif event.num == 5:  # Linux 向下滚动
            scale = 0.9
        elif event.num == 4:  # Linux 向上滚动
            scale = 1.1
        else:
            return

        # 更新缩放因子
        old_zoom = self.zoom_factor
        self.zoom_factor *= scale

        # 限制缩放范围
        self.zoom_factor = max(0.1, min(self.zoom_factor, 10.0))

        # 计算实际缩放比例
        actual_scale = self.zoom_factor / old_zoom

        # 调整偏移量，使缩放以鼠标位置为中心
        self.offset_x = int(mouse_x - (mouse_x - self.offset_x) * actual_scale)
        self.offset_y = int(mouse_y - (mouse_y - self.offset_y) * actual_scale)

        # 更新显示
        self.update_display()
        self.status_bar.config(text=f"缩放: {self.zoom_factor:.1f}x")

    def update_display(self, *args):
        """更新显示"""
        if self.image is None:
            return

        # 复制图像
        display = self.image.copy()

        # 如果有mask，叠加显示
        if self.mask is not None:
            # 创建彩色mask（红色）
            mask_colored = np.zeros_like(display)
            mask_colored[:, :, 0] = self.mask  # 红色通道

            # 叠加mask
            alpha = self.alpha_var.get()
            display = cv2.addWeighted(display, 1, mask_colored, alpha, 0)

        # 调整图像大小以适应画布（考虑缩放因子）
        h, w = display.shape[:2]
        base_scale = min(self.canvas_width / w, self.canvas_height / h)
        scale = base_scale * self.zoom_factor
        new_w = int(w * scale)
        new_h = int(h * scale)

        display = cv2.resize(display, (new_w, new_h))
        self.display_image = display

        # 转换为PIL图像
        pil_image = Image.fromarray(display)
        photo = ImageTk.PhotoImage(pil_image)

        # 在画布上显示（考虑偏移）
        self.canvas.delete("all")
        x = (self.canvas_width - new_w) // 2 + self.offset_x
        y = (self.canvas_height - new_h) // 2 + self.offset_y
        self.canvas.create_image(x, y, anchor=tk.NW, image=photo)
        self.canvas.image = photo


def main():
    root = tk.Tk()
    app = CrackLabeler(root)
    root.mainloop()


if __name__ == "__main__":
    main()
