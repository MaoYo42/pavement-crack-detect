# 基于 U-Net 的高速公路车辆裂缝检测系统 - 业务层升级与论文对标计划

## 一、系统架构决策
**现有高优全栈架构 (FastAPI 一体化)**
*   **选型说明**：避免了沉重的微服务化调度开销，使用纯 Python 栈使前端请求能够内存流式直达底层的 PyTorch 运算核，是目前 AI 领域业界最优实践。相比于老派的 `SpringBoot + Python` 组合，本方案极大降低了进程间通信 (IPC) 延迟，非常契合基于大图语义分割的任务。
*   **前端选型**：纯原生 HTML/CSS/JS + Glassmorphism 现代暗调 UI，完全通过动态渲染 DOM 构建管理页，无需编译与打包，保证项目轻巧和开箱即用。

## 二、严格对标论文的模型设计 (对应 4.3 章节)
*采用 SQLite 单一文件数据库存储以满足即走即用的演示需求*

1.  **`User` (用户表)**：包含 `id`, `username`, `password_hash`, `role` ('user' 或 'admin'), `created_at`。
2.  **`DetectionTask` (识别任务表)**：包含 `id`, `user_id`, `image_path`, `status` (处理中/已完成/失败), `duration_ms` (推理耗时), `created_at`。
3.  **`DetectionResult` (识别结果表)**：包含 `id`, `task_id`, `mask_path`, `overlay_path`, `score` (损伤百分比占比)。
4.  **`SystemLog` (系统日志表)**：包含 `id`, `user_id`, `action`, `created_at`。

## 三、各阶段迭代与模块代码分配方案

### 阶段 1：依赖环境与数据骨架搭设
- 修改 `requirements.txt`：补充引入 `sqlalchemy`, `passlib[bcrypt]`, `pyjwt`。
- 创建 `app/database.py`：设置 SQLite 连接并在启动时建表。
- 创建 `app/models.py`：通过 SQLAlchemy ORM 将上述 4 张表映射为模型类。

### 阶段 2：鉴权体系与安全网关封装 (Security)
- 创建 `app/auth.py`：构建密码哈希策略。
- 在 `auth.py` 基于 `OAuth2PasswordBearer` 构建用户鉴权 (`get_current_user`) 和 管理员鉴权 (`get_current_admin_user`)。

### 阶段 3：后端 API 核心注入与改造 (Controller)
- **更新 `main.py`**：
  1. 开通 `/auth/login` 与 `/auth/register` (并留底到 SystemLog)。
  2. 严给单图及批量推理接口加上 JWT 权限锁。
  3. 修改推理逻辑：任务起始时新建 `DetectionTask`，完毕后新建 `DetectionResult` 落库，统计耗时。
  4. 新增后台大盘接口：`/admin/users`, `/admin/tasks`, `/admin/logs` 及其对应的只读查库层。

### 阶段 4：前端视图拓展与鉴权响应层
- **HTML (`index.html`)**：搭建模态窗（登录/查历史）；通过导航条划分**Admin面板**入口。
- **CSS (`style.css`)**：建立表单 (Form)、多列表格 (Table)、系统日志卡片的统一样式基调。
- **JS (`script.js`)**：编写全局 Fetch 函数来隐式挂载 `Bearer Token`，撰写各面板数据调取的 DOM 动态绑定函数。

---
*文档更新日志：系统依照指导完成双角色权限区分，完全吻合论文 4.3.2 设计章与 5.5 测试章规范。*
