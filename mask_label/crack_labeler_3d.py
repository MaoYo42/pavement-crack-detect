#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路面裂缝 3D 并排分割标注软件
主要功能：并排加载 Gray、Def、Det 三通道图像，共享单层 mask 涂抹与缩放联动。
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import cv2
import numpy as np
from PIL import Image, ImageTk
import os


class CrackLabeler3D:
    def __init__(self, root):
        self.root = root
        self.root.title("路面裂缝3D多模态并排标注工具")

        # 图像相关变量 (原版使用 self.image 和 self.display_image)
        self.images = {'Gray': None, 'Def': None, 'Det': None}
        self.display_images = {'Gray': None, 'Def': None, 'Det': None}
        self.mask = None
        self.image_path = None
        self.mask_path = None
        
        # 用来保存每个Canvas上的PhotoImage引用以防被垃圾回收
        self.photos = {'Gray': None, 'Def': None, 'Det': None}

        # 文件夹批量处理相关变量
        self.project_folder = None
        self.image_folder = None # 默认为 images/Gray
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
            'patched': {'folder': None, 'count': 0, 'desc': '修补', 'prefix': '[P]修补', 'color': 'orange'},
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
        self.canvas_width = 500
        self.canvas_height = 800
        self.zoom_factor = 1.0
        self.offset_x = 0
        self.offset_y = 0
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.is_panning = False
        
        # IDE attributes resolution
        self.tool_var = None
        self.size_var = None
        self.size_label = None
        self.alpha_var = None
        self.prev_btn = None
        self.next_btn = None
        self.file_info_label = None
        self.paned_window = None
        self.canvases = {}
        self.status_bar = None

        self.setup_ui()
        self.setup_shortcuts()

    def setup_ui(self):
        """设置用户界面"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="加载单张图像(仅测试)", command=self.load_image_single)
        file_menu.add_command(label="加载Mask", command=self.load_mask)
        file_menu.add_separator()
        file_menu.add_command(label="加载 3D 项目文件夹", command=self.load_project_folder)
        file_menu.add_separator()
        file_menu.add_command(label="保存Mask", command=self.save_mask)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="快捷键说明", command=self.show_shortcuts_help)

        toolbar = tk.Frame(self.root, relief=tk.RAISED, borderwidth=2)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        tk.Label(toolbar, text="工具:").pack(side=tk.LEFT, padx=5)
        self.tool_var = tk.StringVar(value="brush")
        brush_btn = tk.Radiobutton(toolbar, text="画笔", variable=self.tool_var, value="brush", command=self.change_tool)
        brush_btn.pack(side=tk.LEFT, padx=5)
        eraser_btn = tk.Radiobutton(toolbar, text="橡皮擦", variable=self.tool_var, value="eraser", command=self.change_tool)
        eraser_btn.pack(side=tk.LEFT, padx=5)

        tk.Label(toolbar, text="画笔大小:").pack(side=tk.LEFT, padx=10)
        self.size_var = tk.IntVar(value=10)
        size_scale = tk.Scale(toolbar, from_=1, to=20, orient=tk.HORIZONTAL, variable=self.size_var, command=self.change_brush_size)
        size_scale.pack(side=tk.LEFT, padx=5)
        self.size_label = tk.Label(toolbar, text="10")
        self.size_label.pack(side=tk.LEFT, padx=5)

        tk.Label(toolbar, text="Mask透明度:").pack(side=tk.LEFT, padx=10)
        self.alpha_var = tk.DoubleVar(value=0.5)
        alpha_scale = tk.Scale(toolbar, from_=0, to=1, resolution=0.1, orient=tk.HORIZONTAL, variable=self.alpha_var, command=self.update_display)
        alpha_scale.pack(side=tk.LEFT, padx=5)

        tk.Label(toolbar, text=" | ").pack(side=tk.LEFT, padx=5)
        self.prev_btn = tk.Button(toolbar, text="上一张", command=self.prev_image, state=tk.DISABLED)
        self.prev_btn.pack(side=tk.LEFT, padx=5)
        self.next_btn = tk.Button(toolbar, text="下一张", command=self.next_image, state=tk.DISABLED)
        self.next_btn.pack(side=tk.LEFT, padx=5)
        self.file_info_label = tk.Label(toolbar, text="")
        self.file_info_label.pack(side=tk.LEFT, padx=10)

        tk.Label(toolbar, text=" | ").pack(side=tk.LEFT, padx=5)
        for cat_key, cat_info in self.categories.items():
            lbl = tk.Label(toolbar, text=f"{cat_info['prefix']}:0", fg=str(cat_info['color']))
            lbl.pack(side=tk.LEFT, padx=5)
            self.category_labels[cat_key] = lbl

        # 创建并排的三块画布
        self.paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.canvases = {}
        # 色彩背景加以区分边界
        bgs = {'Gray': '#444444', 'Def': '#555555', 'Det': '#666666'}
        
        for view_name in ['Gray', 'Def', 'Det']:
            frame = tk.Frame(self.paned_window)
            self.paned_window.add(frame, minsize=400)
            
            lbl = tk.Label(frame, text=f"【{view_name}】视图", font=("Arial", 12, "bold"))
            lbl.pack(side=tk.TOP, pady=2)
            
            c = tk.Canvas(frame, width=self.canvas_width, height=self.canvas_height, bg=bgs[view_name])
            c.pack(fill=tk.BOTH, expand=True)
            self.canvases[view_name] = c

            # 全部绑定相同的鼠标事件，确保无论在哪个窗口操作都能生效联动
            c.bind("<Button-1>", self.on_mouse_down)
            c.bind("<B1-Motion>", self.on_mouse_drag)
            c.bind("<ButtonRelease-1>", self.on_mouse_up)
            c.bind("<MouseWheel>", self.on_mouse_wheel)  
            c.bind("<Button-4>", self.on_mouse_wheel)    
            c.bind("<Button-5>", self.on_mouse_wheel)    

        self.status_bar = tk.Label(self.root, text="就绪", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def setup_shortcuts(self):
        """设置快捷键"""
        self.root.bind("<Command-z>", lambda e: self.undo())
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Left>", lambda e: self.prev_image())
        self.root.bind("<Up>", lambda e: self.prev_image())
        self.root.bind("a", lambda e: self.prev_image())
        self.root.bind("A", lambda e: self.prev_image())
        self.root.bind("<Right>", lambda e: self.next_image())
        self.root.bind("<Down>", lambda e: self.next_image())
        self.root.bind("d", lambda e: self.next_image())
        self.root.bind("D", lambda e: self.next_image())
        self.root.bind("w", lambda e: self.toggle_tool())
        self.root.bind("W", lambda e: self.toggle_tool())
        self.root.bind("<KeyPress-s>", lambda e: self.hide_mask())
        self.root.bind("<KeyPress-S>", lambda e: self.hide_mask())
        self.root.bind("<KeyRelease-s>", lambda e: self.show_mask())
        self.root.bind("<KeyRelease-S>", lambda e: self.show_mask())
        self.root.bind("<Delete>", lambda e: self.delete_current_image())
        self.root.bind("<BackSpace>", lambda e: self.delete_current_image())
        self.root.bind("p", lambda e: self.move_to_category('patched'))
        self.root.bind("P", lambda e: self.move_to_category('patched'))
        self.root.bind("t", lambda e: self.move_to_category('true_crack'))
        self.root.bind("T", lambda e: self.move_to_category('true_crack'))
        self.root.bind("f", lambda e: self.move_to_category('false_crack'))
        self.root.bind("F", lambda e: self.move_to_category('false_crack'))

    def load_image_single(self):
        """仅做向后兼容单图测试加载"""
        file_path = filedialog.askopenfilename(title="选择图像文件")
        if file_path:
            self.image_path = file_path
            img = cv2.imread(file_path)
            if img is not None:
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                self.images['Gray'] = img_rgb
                self.images['Def'] = img_rgb
                self.images['Det'] = img_rgb
                self.mask = np.zeros(img_rgb.shape[:2], dtype=np.uint8)
                self.update_display()

    def load_mask(self):
        """加载mask标签"""
        file_path = filedialog.askopenfilename(title="选择Mask文件", filetypes=[("图像文件", "*.jpg *.png *.bmp"), ("所有", "*.*")])
        if file_path:
            self.mask_path = file_path
            mask = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
            if mask is not None:
                if self.images['Gray'] is not None and mask.shape != self.images['Gray'].shape[:2]:
                    mask = cv2.resize(mask, (self.images['Gray'].shape[1], self.images['Gray'].shape[0]))
                self.mask = mask
                self.update_display()
                self.status_bar.config(text=f"已加载Mask: {os.path.basename(file_path)}")

    def load_project_folder(self):
        """加载3D项目文件夹（应包含images/Gray, images/Def, images/Det, masks）"""
        folder_path = filedialog.askdirectory(title="选择 3D 项目文件夹(包含 images 和 masks)")
        if not folder_path:
            self.root.focus_force()
            return

        self.project_folder = folder_path
        images_gray_path = os.path.join(folder_path, "images", "Gray")
        masks_path = os.path.join(folder_path, "masks")

        if not os.path.exists(images_gray_path):
            messagebox.showerror("错误", f"未找到三维图像基准目录：{images_gray_path}\n请确保格式仿照 crack_3d。")
            self.root.focus_force()
            return

        if not os.path.exists(masks_path):
            result = messagebox.askyesno("提示", f"未找到masks子目录：{masks_path}\n是否创建该目录？")
            if result:
                os.makedirs(masks_path)
            else:
                self.root.focus_force()
                return

        self.image_folder = images_gray_path
        self.mask_folder = masks_path

        self.image_files = []
        for ext in ['*.jpg', '*.png', '*.JPG', '*.PNG']:
            self.image_files.extend(sorted([f for f in os.listdir(images_gray_path) if f.lower().endswith(ext[1:])]))

        if not self.image_files:
            messagebox.showwarning("警告", "images/Gray 文件夹中没有找到图像文件")
            self.root.focus_force()
            return

        parent_dir = os.path.dirname(folder_path)
        base_name = os.path.basename(folder_path)
        for cat_key, cat_info in self.categories.items():
            cat_info['folder'] = os.path.join(parent_dir, f"{base_name}_{cat_key}")
            cat_info['count'] = 0
            self.category_labels[cat_key].config(text=f"{cat_info['prefix']}:0")

        self.current_index = 0
        self.load_image_by_index(self.current_index)
        self.update_navigation_buttons()
        self.status_bar.config(text=f"已加载大项目: {folder_path} (共{len(self.image_files)}个目标)")

    def show_shortcuts_help(self):
        """显示快捷键帮助对话框"""
        help_window = tk.Toplevel(self.root)
        help_window.title("3D 快捷键说明")
        help_window.geometry("600x500")
        help_text = "所有的按键操作都与单面一模一样。画布操作在三大视图完全同步联动。"
        text_widget = tk.Text(help_window)
        text_widget.insert("1.0", help_text)
        text_widget.pack(expand=True, fill=tk.BOTH)

    def load_image_by_index(self, index):
        """根据索引载入三个平行维度的图像及Mask"""
        if index < 0 or index >= len(self.image_files):
            return

        gray_name = self.image_files[index]
        gray_path = os.path.join(self.image_folder, gray_name)

        img_gray = cv2.imread(gray_path)
        if img_gray is None:
            messagebox.showerror("错误", f"无法加载基准图像: {gray_name}")
            return
        
        self.images['Gray'] = cv2.cvtColor(img_gray, cv2.COLOR_BGR2RGB)

        # 尝试推导 Def 和 Det
        def_name = gray_name.replace('Gray', 'Def')
        det_name = gray_name.replace('Gray', 'Det')
        
        img_parent = os.path.dirname(self.image_folder) # images/
        def_path = os.path.join(img_parent, "Def", def_name)
        det_path = os.path.join(img_parent, "Det", det_name)

        def safe_load(path, fallback_shape):
            if os.path.exists(path):
                img = cv2.imread(path)
                if img is not None:
                    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            return np.zeros(fallback_shape, dtype=np.uint8)

        self.images['Def'] = safe_load(def_path, img_gray.shape)
        self.images['Det'] = safe_load(det_path, img_gray.shape)

        self.undo_stack = []
        self.zoom_factor = 1.0
        self.offset_x = 0
        self.offset_y = 0

        self.load_mask_by_index(index)
        self.update_display()
        self.file_info_label.config(text=f"{index + 1}/{len(self.image_files)}")
        self.status_bar.config(text=f"已加载三维组: {gray_name.replace('Gray', '*')}")
        self.root.focus_force()

    def load_mask_by_index(self, index):
        gray_name = self.image_files[index]
        base_name = os.path.splitext(gray_name)[0]
        
        mask_found = False
        if self.mask_folder:
            for ext in ['.png', '.jpg']:
                mask_path = os.path.join(self.mask_folder, base_name + ext)
                if os.path.exists(mask_path):
                    m = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
                    if m is not None:
                        if self.images['Gray'] is not None and m.shape != self.images['Gray'].shape[:2]:
                            m = cv2.resize(m, (self.images['Gray'].shape[1], self.images['Gray'].shape[0]))
                        self.mask = m
                        mask_found = True
                        break

        if not mask_found:
            self.mask = np.zeros(self.images['Gray'].shape[:2], dtype=np.uint8)

    def prev_image(self):
        if self.current_index > 0:
            if self.mask is not None and self.mask_folder:
                self.auto_save_mask()
            self.current_index -= 1
            self.load_image_by_index(self.current_index)
            self.update_navigation_buttons()

    def next_image(self):
        if self.current_index < len(self.image_files) - 1:
            if self.mask is not None and self.mask_folder:
                self.auto_save_mask()
            self.current_index += 1
            self.load_image_by_index(self.current_index)
            self.update_navigation_buttons()

    def delete_current_image(self):
        messagebox.showinfo("安全拦截", "四维数据删除逻辑极为危险，为了防止破坏结构，在3D模式下暂不提供快捷删除。")

    def update_navigation_buttons(self):
        if len(self.image_files) > 0:
            self.prev_btn.config(state=tk.NORMAL if self.current_index > 0 else tk.DISABLED)
            self.next_btn.config(state=tk.NORMAL if self.current_index < len(self.image_files) - 1 else tk.DISABLED)

    def auto_save_mask(self):
        if self.mask is None or not self.mask_folder:
            return
        image_name = self.image_files[self.current_index]
        base_name = os.path.splitext(image_name)[0]
        mask_path = os.path.join(self.mask_folder, base_name + '.png')
        cv2.imwrite(mask_path, self.mask)

    def save_mask(self):
        if self.mask_folder and self.image_files:
            self.auto_save_mask()
            self.status_bar.config(text="全维数据 Mask 已安全自动落盘。")

    def change_tool(self):
        self.current_tool = self.tool_var.get()

    def toggle_tool(self):
        if self.current_tool == "brush":
            self.tool_var.set("eraser")
            self.current_tool = "eraser"
        else:
            self.tool_var.set("brush")
            self.current_tool = "brush"

    def hide_mask(self):
        if self.is_mask_hidden: return
        self.is_mask_hidden = True
        self.saved_alpha = self.alpha_var.get()
        self.alpha_var.set(0)
        self.update_display()

    def show_mask(self):
        self.is_mask_hidden = False
        self.alpha_var.set(self.saved_alpha)
        self.update_display()

    def move_to_category(self, category_key):
        messagebox.showinfo("暂不支持", "在3D架构下，分类移动需要迁移极大量对应文件关联。为了避免损坏现存庞大图库，暂不开放直接分类移动。")

    def change_brush_size(self, value):
        self.brush_size = int(float(value))
        self.size_label.config(text=str(self.brush_size))

    def save_undo_state(self):
        if self.mask is not None:
            self.undo_stack.append(self.mask.copy())
            if len(self.undo_stack) > self.max_undo_steps:
                self.undo_stack.pop(0)

    def undo(self):
        if len(self.undo_stack) > 0:
            self.mask = self.undo_stack.pop()
            self.update_display()

    def on_mouse_down(self, event):
        if self.images['Gray'] is None or self.mask is None:
            return
        self.save_undo_state()
        self.drawing = True
        self.last_x = event.x
        self.last_y = event.y
        self.draw_on_mask(event.x, event.y)

    def on_mouse_drag(self, event):
        if not self.drawing or self.images['Gray'] is None or self.mask is None:
            return
        if self.last_x is not None and self.last_y is not None:
            self.draw_line_on_mask(self.last_x, self.last_y, event.x, event.y)
        self.last_x = event.x
        self.last_y = event.y

    def on_mouse_up(self, event):
        self.drawing = False
        self.last_x = None
        self.last_y = None

    def draw_on_mask(self, canvas_x, canvas_y):
        img_x, img_y = self.canvas_to_image_coords(canvas_x, canvas_y)
        if img_x < 0 or img_y < 0 or img_x >= self.mask.shape[1] or img_y >= self.mask.shape[0]:
            return
        color = 255 if self.current_tool == "brush" else 0
        cv2.circle(self.mask, (img_x, img_y), self.brush_size, color, -1)
        self.update_display()

    def draw_line_on_mask(self, x1, y1, x2, y2):
        img_x1, img_y1 = self.canvas_to_image_coords(x1, y1)
        img_x2, img_y2 = self.canvas_to_image_coords(x2, y2)
        color = 255 if self.current_tool == "brush" else 0
        cv2.line(self.mask, (img_x1, img_y1), (img_x2, img_y2), color, self.brush_size * 2)
        self.update_display()

    def canvas_to_image_coords(self, canvas_x, canvas_y):
        if self.display_images['Gray'] is None or self.images['Gray'] is None:
            return 0, 0
            
        # 因三个 Canvas 的显示大小与内容一致，可随意选用 Gray 的属性估算
        display_h, display_w = self.display_images['Gray'].shape[:2]

        current_canvas_w = self.canvases['Gray'].winfo_width()
        current_canvas_h = self.canvases['Gray'].winfo_height()
        if current_canvas_w < 10: current_canvas_w = self.canvas_width
        if current_canvas_h < 10: current_canvas_h = self.canvas_height

        x_offset = (current_canvas_w - display_w) // 2 + self.offset_x
        y_offset = (current_canvas_h - display_h) // 2 + self.offset_y

        display_x = canvas_x - x_offset
        display_y = canvas_y - y_offset

        scale_x = self.images['Gray'].shape[1] / max(1, display_w)
        scale_y = self.images['Gray'].shape[0] / max(1, display_h)

        return int(display_x * scale_x), int(display_y * scale_y)

    def on_mouse_wheel(self, event):
        if self.images['Gray'] is None:
            return

        mouse_x = event.x
        mouse_y = event.y

        if hasattr(event, 'delta') and event.delta != 0:
            if event.delta > 0:
                scale = 1.1 if abs(event.delta) > 50 else 1.0 + abs(event.delta) / 1000
            else:
                scale = 0.9 if abs(event.delta) > 50 else 1.0 - abs(event.delta) / 1000
        elif event.num == 5:
            scale = 0.9
        elif event.num == 4:
            scale = 1.1
        else:
            return

        old_zoom = self.zoom_factor
        self.zoom_factor = max(0.1, min(self.zoom_factor * scale, 10.0))
        actual_scale = self.zoom_factor / old_zoom

        self.offset_x = int(mouse_x - (mouse_x - self.offset_x) * actual_scale)
        self.offset_y = int(mouse_y - (mouse_y - self.offset_y) * actual_scale)

        self.update_display()
        self.status_bar.config(text=f"超清三屏全息缩放锁定: {self.zoom_factor:.1f}x")

    def update_display(self, *args):
        if self.images['Gray'] is None:
            return

        alpha = self.alpha_var.get()

        for view_name in ['Gray', 'Def', 'Det']:
            base_img = self.images[view_name]
            if base_img is None: continue
            
            display = base_img.copy()
            if self.mask is not None:
                mask_colored = np.zeros_like(display)
                mask_colored[:, :, 0] = self.mask  # 红
                display = cv2.addWeighted(display, 1, mask_colored, alpha, 0)
                
            current_canvas_w = self.canvases[view_name].winfo_width()
            current_canvas_h = self.canvases[view_name].winfo_height()
            
            # 兼容启动时的 0 和 1
            if current_canvas_w < 10: current_canvas_w = self.canvas_width
            if current_canvas_h < 10: current_canvas_h = self.canvas_height

            h, w = display.shape[:2]
            base_scale = min(current_canvas_w / w, current_canvas_h / h)
            scale = base_scale * self.zoom_factor
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))

            display = cv2.resize(display, (new_w, new_h))
            self.display_images[view_name] = display

            pil_image = Image.fromarray(display)
            photo = ImageTk.PhotoImage(pil_image)
            self.photos[view_name] = photo # Keep reference

            canvas = self.canvases[view_name]
            canvas.delete("all")
            x = (current_canvas_w - new_w) // 2 + self.offset_x
            y = (current_canvas_h - new_h) // 2 + self.offset_y
            canvas.create_image(x, y, anchor=tk.NW, image=photo)

def main():
    root = tk.Tk()
    root.geometry("1400x800")
    app = CrackLabeler3D(root)
    root.mainloop()

if __name__ == "__main__":
    main()
