const tabs = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');

let currentToken = localStorage.getItem('token') || null;
let currentRole = localStorage.getItem('role') || 'user';
let currentUsername = localStorage.getItem('username') || '';

const authModal = document.getElementById('auth-modal');
const mainDashboard = document.getElementById('main-dashboard');
const userPanel = document.getElementById('user-panel');
const adminTabBtn = document.querySelector('.admin-only');
const resultsPanel = document.getElementById('results-panel');

const authTitle = document.getElementById('auth-title');
const authUser = document.getElementById('auth-username');
const authPass = document.getElementById('auth-password');
const authRole = document.getElementById('auth-role');
const historyDetailModal = document.getElementById('history-detail-modal');
const historyDetailMeta = document.getElementById('history-detail-meta');
const detailOrigImg = document.getElementById('detail-orig-img');
const detailMaskImg = document.getElementById('detail-mask-img');
const detailOverlayImg = document.getElementById('detail-overlay-img');
const adminUserModal = document.getElementById('admin-user-modal');
const adminUserModalTitle = document.getElementById('admin-user-modal-title');
const adminUserIdInput = document.getElementById('admin-user-id');
const adminUserUsernameInput = document.getElementById('admin-user-username');
const adminUserPasswordInput = document.getElementById('admin-user-password');
const adminUserRoleInput = document.getElementById('admin-user-role');
const adminUserActiveInput = document.getElementById('admin-user-active');
const historyStartDate = document.getElementById('history-start-date');
const historyEndDate = document.getElementById('history-end-date');
const historyStatus = document.getElementById('history-status');
let authMode = 'login';
let historyFilters = { start_date: '', end_date: '', status: 'all' };
let adminUsersCache = [];
let adminCurrentSubtab = 'users';
let adminUserModalMode = 'create';
let adminEditingUserId = null;

async function fetchWithAuth(url, options = {}) {
    if (currentToken) {
        options.headers = options.headers || {};
        options.headers['Authorization'] = `Bearer ${currentToken}`;
    }
    const response = await fetch(url, options);
    if (response.status === 401) {
        logout();
    }
    return response;
}

function formatDisplayDate(value) {
    if (!value) return '-';
    const normalized = String(value).replace(' ', 'T');
    const date = new Date(normalized);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
    });
}

function numberOrDash(value, digits = 0) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
    return Number(value).toFixed(digits);
}

function renderBadges(containerId, items) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = items.map(item => `
        <span class="badge-chip ${item.muted ? 'muted' : ''}">
            ${item.icon ? `<i class="${item.icon}"></i>` : ''}
            <span>${item.label}</span>
            ${item.value !== undefined ? `<strong>${item.value}</strong>` : ''}
        </span>
    `).join('');
}

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function buildQueryString(params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && String(value).trim() !== '') {
            searchParams.set(key, value);
        }
    });
    const query = searchParams.toString();
    return query ? `?${query}` : '';
}

function formatDuration(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
    return `${Number(value).toFixed(0)} ms`;
}

function syncResultsPanelVisibility() {
    const activeTab = document.querySelector('.tab-btn.active');
    const showResults = activeTab && activeTab.dataset.target === '#tab-single';
    if (resultsPanel) {
        resultsPanel.classList.toggle('hidden', !showResults);
    }
    if (mainDashboard) {
        mainDashboard.classList.toggle('results-hidden', !showResults);
    }
}

function checkLoginState() {
    if (currentToken) {
        userPanel.innerHTML = `
            <span class="user-greeting">欢迎, ${currentUsername}
                ${currentRole === 'admin' ? '<span class="role-badge">Admin</span>' : ''}
            </span>
            <button class="btn secondary small-btn" onclick="logout()">退出</button>
        `;
        mainDashboard.style.display = 'grid';
        if (currentRole === 'admin') {
            adminTabBtn.style.display = 'inline-block';
        } else {
            adminTabBtn.style.display = 'none';
        }
    } else {
        userPanel.innerHTML = `
            <button class="btn secondary small-btn" onclick="openAuthModal('login')">登录</button>
            <button class="btn primary small-btn" onclick="openAuthModal('register')">注册</button>
        `;
        mainDashboard.style.display = 'none';
    }
}

function openAuthModal(mode) {
    authMode = mode;
    authTitle.innerText = mode === 'login' ? '系统登录' : '创建普通用户账号';
    authRole.style.display = mode === 'register' ? 'block' : 'none';
    authModal.classList.add('active');
}

function closeAuthModal() {
    authModal.classList.remove('active');
    authUser.value = '';
    authPass.value = '';
}

async function submitAuth() {
    const username = authUser.value.trim();
    const password = authPass.value.trim();
    if (!username || !password) return alert("账号和密码不能为空");

    if (authMode === 'register') {
        const res = await fetch('/auth/register', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username, password})
        });
        if (res.ok) {
            alert("注册成功，请登录");
            openAuthModal('login');
        } else {
            const data = await res.json();
            alert("注册失败: " + data.detail);
        }
    } else {
        const formData = new FormData();
        formData.append('username', username);
        formData.append('password', password);
        const res = await fetch('/auth/login', {
            method: 'POST',
            body: formData
        });
        if (res.ok) {
            const data = await res.json();
            currentToken = data.access_token;
            currentRole = data.role;
            currentUsername = data.username;
            localStorage.setItem('token', currentToken);
            localStorage.setItem('role', currentRole);
            localStorage.setItem('username', currentUsername);
            closeAuthModal();
            checkLoginState();
        } else {
            alert("登录失败，请检查账号密码");
        }
    }
}

function logout() {
    currentToken = null;
    currentRole = 'user';
    localStorage.removeItem('token');
    localStorage.removeItem('role');
    localStorage.removeItem('username');
    checkLoginState();
}

tabs.forEach((tab) => {
    tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        tabContents.forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.querySelector(tab.dataset.target).classList.add('active');
        syncResultsPanelVisibility();
    });
});

const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const analyzeBtn = document.getElementById('analyze-btn');
const clearBtn = document.getElementById('clear-btn');
const loader = document.getElementById('loader');
let selectedFile = null;

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(name => dropZone.addEventListener(name, e => {e.preventDefault(); e.stopPropagation();}, false));
dropZone.addEventListener('drop', (e) => handleFiles(e.dataTransfer.files));
dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', function() { handleFiles(this.files); });

function handleFiles(files) {
    if (!files || !files.length) return;
    selectedFile = files[0];
    const reader = new FileReader();
    reader.onload = (e) => {
        let oldImg = dropZone.querySelector('.drop-preview');
        if(oldImg) oldImg.remove();
        const img = document.createElement('img');
        img.src = e.target.result;
        img.className = 'drop-preview';
        dropZone.appendChild(img);
        analyzeBtn.disabled = false;
    };
    reader.readAsDataURL(selectedFile);
}

clearBtn.addEventListener('click', () => {
    selectedFile = null; fileInput.value = '';
    let p = dropZone.querySelector('.drop-preview'); if(p) p.remove();
    analyzeBtn.disabled = true;
    resetStats();
});

analyzeBtn.addEventListener('click', async () => {
    if (!selectedFile) return;
    loader.classList.add('active');
    document.getElementById('loading-text').innerText = '单图推理';
    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
        const res = await fetchWithAuth('/predict/', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.status !== 'success') throw new Error(data.message || '推理失败');

        document.getElementById('empty-state').style.display = 'none';
        document.getElementById('image-wrapper').style.display = 'block';
        document.getElementById('hint-text').style.display = 'block';

        document.getElementById('orig-img').src = data.original_url;
        document.getElementById('mask-overlay').src = data.overlay_url || data.mask_url;

        document.getElementById('damage-percent').innerText = data.overall_damage_percent.toFixed(2) + '%';
        document.getElementById('mask-area').innerText = data.mask_area;
        document.getElementById('image-size').innerText = `${data.image_width} x ${data.image_height}`;
    } catch (e) {
        alert("推理失败: " + e.message);
    } finally {
        loader.classList.remove('active');
    }
});

let batchSource = null;
const batchStartBtn = document.getElementById('batch-start-btn');
const folderInput = document.getElementById('folder-path');

document.getElementById('browse-btn').addEventListener('click', async () => {
    try {
        const res = await fetchWithAuth('/ask_folder/');
        const data = await res.json();
        if (data.path) folderInput.value = data.path;
    } catch (e) {
        alert("获取文件路径失败，请手动输入");
    }
});

function setBatchRunning(running) {
    if (!batchStartBtn) return;
    batchStartBtn.disabled = running;
    batchStartBtn.style.opacity = running ? '0.65' : '';
}

function appendBatchLog(text) {
    const log = document.getElementById('batch-log');
    if (!log) return;
    const line = document.createElement('div');
    line.textContent = text;
    log.appendChild(line);
    log.scrollTop = log.scrollHeight;
}

function resetBatchProgress() {
    const bar = document.getElementById('batch-progress');
    if (bar) bar.style.width = '0%';
}

batchStartBtn.addEventListener('click', () => {
    if (!currentToken) {
        alert('请先登录后再启动批处理');
        return;
    }
    const path = folderInput.value.trim();
    if (!path) return alert("请输入路径");
    if (batchSource) {
        batchSource.close();
        batchSource = null;
    }

    const statusEl = document.getElementById('batch-status-text');
    document.getElementById('batch-log').innerHTML = '';
    resetBatchProgress();
    if (statusEl) statusEl.textContent = '正在连接服务器…';
    setBatchRunning(true);

    const tokenParam = encodeURIComponent(currentToken);
    const url = `/predict_batch_stream/?folder_path=${encodeURIComponent(path)}&token=${tokenParam}`;
    batchSource = new EventSource(url);

    let batchEnded = false;
    const finishBatch = () => {
        if (batchEnded) return;
        batchEnded = true;
        setBatchRunning(false);
        if (batchSource) {
            batchSource.close();
            batchSource = null;
        }
    };

    batchSource.onmessage = (e) => {
        let data;
        try {
            data = JSON.parse(e.data);
        } catch {
            appendBatchLog('[parse] 无法解析服务器消息');
            return;
        }

        const bar = document.getElementById('batch-progress');

        if (data.event === 'file_error') {
            const msg = data.message || '处理失败';
            appendBatchLog(`[file_error] ${data.file || ''}: ${msg}`);
            if (statusEl) statusEl.textContent = `跳过：${data.file || ''}（其余继续）`;
            return;
        }

        if (data.event === 'error') {
            const msg = data.message || data.detail || '未知错误';
            appendBatchLog(`[error] ${data.file ? data.file + ': ' : ''}${msg}`);
            if (statusEl) statusEl.textContent = `出错：${msg}`;
            finishBatch();
            return;
        }

        if (data.event === 'start') {
            const total = data.total ?? 0;
            appendBatchLog(`[start] 共 ${total} 张，输出目录：${data.batch_dir || ''}`);
            if (statusEl) statusEl.textContent = `批处理中 0 / ${total}`;
            if (bar && total > 0) bar.style.width = '0%';
            return;
        }

        if (data.event === 'progress') {
            const total = Number(data.total) || 1;
            const current = Number(data.current) || 0;
            const pct = Math.min(100, Math.round((current / total) * 100));
            if (bar) bar.style.width = `${pct}%`;
            if (statusEl) {
                statusEl.textContent = `批处理中 ${current} / ${total} · ${data.file || ''}`;
            }
            const dmg = data.damage_percent != null ? ` 损伤 ${Number(data.damage_percent).toFixed(2)}%` : '';
            appendBatchLog(`[progress] ${current}/${total} ${data.file || ''}${dmg}`);
            return;
        }

        if (data.event === 'done') {
            const total = data.total != null ? data.total : '';
            appendBatchLog(`[done] 已完成${total !== '' ? `，共 ${total} 张` : ''}`);
            if (statusEl) statusEl.textContent = '批处理已完成';
            if (bar) bar.style.width = '100%';
            finishBatch();
        }
    };

    batchSource.onerror = () => {
        if (batchEnded) return;
        appendBatchLog('[error] 连接中断或服务不可用（请确认已登录且后端在运行）');
        if (statusEl) statusEl.textContent = '连接中断';
        finishBatch();
    };
});

document.getElementById('history-filter-btn').addEventListener('click', () => {
    fetchMyHistory({
        start_date: historyStartDate.value || '',
        end_date: historyEndDate.value || '',
        status: historyStatus.value || 'all',
    });
});

document.getElementById('history-reset-btn').addEventListener('click', () => {
    historyStartDate.value = '';
    historyEndDate.value = '';
    historyStatus.value = 'all';
    fetchMyHistory({ start_date: '', end_date: '', status: 'all' });
});

historyDetailModal.addEventListener('click', (event) => {
    if (event.target === historyDetailModal) closeHistoryDetailModal();
});

adminUserModal.addEventListener('click', (event) => {
    if (event.target === adminUserModal) closeAdminUserModal();
});

async function fetchMyHistory(overrideFilters = null) {
    const filters = overrideFilters || {
        start_date: historyStartDate?.value || '',
        end_date: historyEndDate?.value || '',
        status: historyStatus?.value || 'all',
    };
    historyFilters = { ...filters };

    const res = await fetchWithAuth(`/history/me${buildQueryString(filters)}`);
    if (!res.ok) return;
    const data = await res.json();
    const history = Array.isArray(data.history) ? data.history : [];
    const total = history.length;
    const completed = history.filter(h => h.status === '已完成').length;
    const avgDuration = total
        ? history.reduce((sum, h) => sum + (Number(h.duration_ms) || 0), 0) / total
        : 0;
    const latest = history[0]?.created_at || '-';

    renderBadges('history-summary-badges', [
        { icon: 'fa-regular fa-clock', label: '记录数', value: total },
        { icon: 'fa-solid fa-circle-check', label: '已完成', value: completed },
        { icon: 'fa-solid fa-stopwatch', label: '平均耗时', value: `${numberOrDash(avgDuration, 0)} ms`, muted: true },
        { icon: 'fa-solid fa-calendar-day', label: '最新记录', value: formatDisplayDate(latest), muted: true },
    ]);

    const container = document.getElementById('history-container');
    if (!history.length) {
        container.innerHTML = `
            <div class="empty-table-state">
                <i class="fa-regular fa-folder-open"></i>
                <div>当前还没有历史记录</div>
                <div>完成一次单图推理或批量处理后，这里会自动显示。</div>
            </div>
        `;
        return;
    }

    let html = `
        <div class="table-topbar">
            <h3>历史记录明细</h3>
            <span>共 ${total} 条</span>
        </div>
        <div class="table-container">
            <table>
                <tr><th>时间</th><th>原图路径</th><th>状态</th><th>耗时(ms)</th><th>损伤%</th><th>操作</th></tr>`;
    history.forEach(h => {
        const statusClass = h.status === '已完成' ? 'ok' : (h.status === '失败' ? 'bad' : 'warn');
        html += `<tr>
            <td>${formatDisplayDate(h.created_at)}</td>
            <td>${escapeHtml(h.image_path || '-')}</td>
            <td><span class="status-pill ${statusClass}">${h.status || '-'}</span></td>
            <td>${numberOrDash(h.duration_ms, 0)}</td>
            <td>${numberOrDash(h.score, 2)}</td>
            <td>
                <button class="table-action-btn" onclick="openHistoryDetail(${h.task_id})">查看详情</button>
            </td>
        </tr>`;
    });
    html += `</table></div>`;
    container.innerHTML = html;
}

const adminSubTabBtns = document.querySelectorAll('.admin-subtab-btn');
async function switchAdminSubtab(type, triggerEvent = null) {
    adminCurrentSubtab = type;
    adminSubTabBtns.forEach(b => b.classList.toggle('active', b.dataset.subtab === type));
    const container = document.getElementById('admin-data-container');
    container.innerHTML = '<p style="padding:1rem;">载入中...</p>';

    try {
        const res = await fetchWithAuth(`/admin/${type}`);
        const data = await res.json();
        let summary = [];
        let html = '';
        if (type === 'users') {
            const users = Array.isArray(data.users) ? data.users : [];
            adminUsersCache = users;
            const admins = users.filter(u => u.role === 'admin').length;
            summary = [
                { icon: 'fa-regular fa-user', label: '用户总数', value: users.length },
                { icon: 'fa-solid fa-user-shield', label: '管理员', value: admins },
                { icon: 'fa-solid fa-users', label: '普通用户', value: users.length - admins, muted: true },
            ];
            html = `<div class="table-topbar">
                <h3>用户管理</h3>
                <div class="table-actions">
                    <button class="table-action-btn" onclick="openAdminUserModal()">新增用户</button>
                </div>
            </div>
            <div class="table-container"><table><tr><th>用户ID</th><th>账号名</th><th>角色</th><th>状态</th><th>注册时间</th><th>操作</th></tr>`;
            users.forEach(u => html += `<tr>
                <td>${u.id}</td>
                <td>${escapeHtml(u.username)}</td>
                <td><span class="status-pill ${u.role === 'admin' ? 'ok' : 'neutral'}">${u.role}</span></td>
                <td><span class="status-pill ${u.is_active ? 'ok' : 'bad'}">${u.is_active ? '启用' : '停用'}</span></td>
                <td>${formatDisplayDate(u.created)}</td>
                <td>
                    <div class="table-actions">
                        <button class="table-action-btn" onclick="openAdminUserModalById(${u.id})">编辑</button>
                        <button class="table-action-btn ${u.is_active ? '' : 'danger'}" onclick="toggleUserStatus(${u.id}, ${u.is_active ? 'false' : 'true'})">${u.is_active ? '停用' : '启用'}</button>
                        <button class="table-action-btn danger" onclick="deleteAdminUser(${u.id})">删除</button>
                    </div>
                </td>
            </tr>`);
            html += `</table></div>`;
        } else if (type === 'tasks') {
            const tasks = Array.isArray(data.tasks) ? data.tasks : [];
            const finished = tasks.filter(t => t.status === '已完成').length;
            summary = [
                { icon: 'fa-solid fa-layer-group', label: '任务总数', value: tasks.length },
                { icon: 'fa-solid fa-circle-check', label: '已完成', value: finished },
                { icon: 'fa-solid fa-spinner', label: '处理中', value: tasks.length - finished, muted: true },
            ];
            html = `<div class="table-topbar">
                <h3>全局任务</h3>
                <span>最近的推理任务</span>
            </div>
            <div class="table-container"><table><tr><th>任务ID</th><th>发起人</th><th>图像路径</th><th>状态</th><th>处理时间</th><th>操作</th></tr>`;
            tasks.forEach(t => html += `<tr>
                <td>${t.task_id}</td>
                <td>${escapeHtml(t.user)}</td>
                <td>${escapeHtml(t.image_path)}</td>
                <td><span class="status-pill ${t.status === '已完成' ? 'ok' : (t.status === '失败' ? 'bad' : 'warn')}">${t.status}</span></td>
                <td>${formatDisplayDate(t.created_at)}</td>
                <td><button class="table-action-btn danger" onclick="deleteAdminTask(${t.task_id})">删除</button></td>
            </tr>`);
            html += `</table></div>`;
        } else if (type === 'logs') {
            const logs = Array.isArray(data.logs) ? data.logs : [];
            summary = [
                { icon: 'fa-regular fa-file-lines', label: '日志总数', value: logs.length },
                { icon: 'fa-solid fa-bell', label: '最新时间', value: logs[0]?.time ? formatDisplayDate(logs[0].time) : '-', muted: true },
            ];
            html = `<div class="table-topbar"><h3>系统日志</h3><span>最近 100 条</span></div><div class="table-container"><table><tr><th>日志ID</th><th>操作人</th><th>行为描述</th><th>操作时间</th></tr>`;
            logs.forEach(l => html += `<tr><td>${l.id}</td><td>${escapeHtml(l.user)}</td><td>${escapeHtml(l.action)}</td><td>${formatDisplayDate(l.time)}</td></tr>`);
            html += `</table></div>`;
        } else if (type === 'system') {
            const summaryItems = [
                { icon: 'fa-solid fa-brain', label: '模型状态', value: data.model_loaded ? '已加载' : '未加载' },
                { icon: 'fa-solid fa-database', label: '数据库', value: data.database_status || '-' },
                { icon: 'fa-solid fa-folder-open', label: '输出目录', value: data.output_dir ? '已配置' : '-' },
            ];
            summary = summaryItems;
            const rows = [
                ['模型路径', data.model_path],
                ['数据库路径', data.database_path],
                ['数据库状态', data.database_status],
                ['输出目录', data.output_dir],
                ['运行目录', data.runtime_dir],
                ['设备', data.device],
                ['最大上传限制', `${data.max_upload_mb} MB`],
                ['允许扩展名', Array.isArray(data.allowed_extensions) ? data.allowed_extensions.join(', ') : '-'],
                ['CORS 来源', Array.isArray(data.allow_origins) ? data.allow_origins.join(', ') : '-'],
            ];
            html = `<div class="table-topbar"><h3>系统配置</h3><span>运行状态与环境信息</span></div><div class="table-container"><table><tr><th>配置项</th><th>值</th></tr>`;
            rows.forEach(([label, value]) => html += `<tr><td>${label}</td><td>${escapeHtml(value ?? '-')}</td></tr>`);
            html += `</table></div>`;
        }
        renderBadges('admin-summary-badges', summary);
        if ((type === 'users' && !data.users?.length) || (type === 'tasks' && !data.tasks?.length) || (type === 'logs' && !data.logs?.length)) {
            html += `<div class="empty-table-state"><i class="fa-regular fa-folder-open"></i><div>暂无数据</div></div>`;
        }
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<div class="empty-table-state"><i class="fa-solid fa-triangle-exclamation"></i><div>权限阻断或加载失败</div></div>`;
    }
}

async function fetchAdminData() {
    switchAdminSubtab(adminCurrentSubtab || 'users');
}

function openHistoryDetailModal() {
    historyDetailModal.classList.add('active');
}

function closeHistoryDetailModal() {
    historyDetailModal.classList.remove('active');
}

function setModalImage(imgEl, url) {
    if (!url) {
        imgEl.removeAttribute('src');
        imgEl.style.display = 'none';
        return;
    }
    imgEl.style.display = 'block';
    imgEl.src = url;
}

function renderHistoryDetail(data) {
    const items = [
        ['任务编号', data.task_id],
        ['用户', data.user],
        ['状态', data.status],
        ['耗时', formatDuration(data.duration_ms)],
        ['时间', formatDisplayDate(data.created_at)],
        ['损伤占比', data.score === null || data.score === undefined ? '-' : `${Number(data.score).toFixed(2)}%`],
        ['原图路径', data.image_path],
        ['Mask 路径', data.mask_path],
        ['叠加图路径', data.overlay_path],
    ];
    historyDetailMeta.innerHTML = items.map(([label, value]) => `
        <div class="meta-item">
            <span class="meta-label">${label}</span>
            <div class="meta-value">${escapeHtml(value)}</div>
        </div>
    `).join('');
    setModalImage(detailOrigImg, data.image_path);
    setModalImage(detailMaskImg, data.mask_path);
    setModalImage(detailOverlayImg, data.overlay_path);
    openHistoryDetailModal();
}

async function openHistoryDetail(taskId) {
    const res = await fetchWithAuth(`/history/detail/${taskId}`);
    if (!res.ok) {
        alert('历史记录详情加载失败');
        return;
    }
    renderHistoryDetail(await res.json());
}

function openAdminUserModal(user = null) {
    adminUserModalMode = user ? 'edit' : 'create';
    adminEditingUserId = user ? user.id : null;
    adminUserModalTitle.innerText = user ? `编辑用户 #${user.id}` : '创建用户';
    adminUserIdInput.value = user ? user.id : '';
    adminUserUsernameInput.value = user ? user.username : '';
    adminUserPasswordInput.value = '';
    adminUserRoleInput.value = user ? user.role : 'user';
    adminUserActiveInput.checked = user ? !!user.is_active : true;
    adminUserPasswordInput.placeholder = user ? '密码，不修改可留空' : '初始密码';
    adminUserModal.classList.add('active');
}

function openAdminUserModalById(userId) {
    const user = adminUsersCache.find(item => item.id === userId);
    if (!user) return alert('用户信息未找到');
    openAdminUserModal(user);
}

function closeAdminUserModal() {
    adminUserModal.classList.remove('active');
    adminEditingUserId = null;
    adminUserModalMode = 'create';
}

async function saveAdminUser() {
    const username = adminUserUsernameInput.value.trim();
    const password = adminUserPasswordInput.value.trim();
    const role = adminUserRoleInput.value;
    const is_active = adminUserActiveInput.checked;

    if (!username) return alert('用户名不能为空');
    if (adminUserModalMode === 'create' && !password) return alert('新建用户时密码不能为空');

    const payload = { username, role, is_active };
    if (password) payload.password = password;

    const url = adminUserModalMode === 'create'
        ? '/admin/users'
        : `/admin/users/${adminEditingUserId}`;
    const method = adminUserModalMode === 'create' ? 'POST' : 'PUT';

    const res = await fetchWithAuth(url, {
        method,
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
    });
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        alert(data.detail || '保存失败');
        return;
    }
    closeAdminUserModal();
    await switchAdminSubtab('users');
}

async function toggleUserStatus(userId, active) {
    const endpoint = active ? 'enable' : 'disable';
    const res = await fetchWithAuth(`/admin/users/${userId}/${endpoint}`, { method: 'PATCH' });
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        alert(data.detail || '状态修改失败');
        return;
    }
    await switchAdminSubtab('users');
}

async function deleteAdminUser(userId) {
    if (!confirm('确定删除该用户吗？该用户的历史记录和日志也会一并清理。')) return;
    const res = await fetchWithAuth(`/admin/users/${userId}`, { method: 'DELETE' });
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        alert(data.detail || '删除失败');
        return;
    }
    await switchAdminSubtab('users');
}

async function deleteAdminTask(taskId) {
    if (!confirm('确定删除该任务吗？关联文件也会清理。')) return;
    const res = await fetchWithAuth(`/admin/tasks/${taskId}`, { method: 'DELETE' });
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        alert(data.detail || '删除失败');
        return;
    }
    await switchAdminSubtab('tasks');
}

function isTypingElement(el) {
    if (!el || el.isContentEditable) return true;
    const t = el.tagName;
    return t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT';
}

function shouldHandleMaskHotkey() {
    const wrapper = document.getElementById('image-wrapper');
    const ov = document.getElementById('mask-overlay');
    if (!wrapper || !ov) return false;
    if (wrapper.style.display === 'none') return false;
    const src = ov.getAttribute('src');
    return Boolean(src && src.trim() !== '');
}

document.addEventListener('keydown', (e) => {
    if (e.code !== 'Space' && e.key !== ' ') return;
    if (isTypingElement(e.target)) return;
    if (!shouldHandleMaskHotkey()) return;
    e.preventDefault();
    e.stopPropagation();
    const ov = document.getElementById('mask-overlay');
    if (ov) ov.style.opacity = '0';
});
document.addEventListener('keyup', (e) => {
    if (e.code !== 'Space' && e.key !== ' ') return;
    if (isTypingElement(e.target)) return;
    if (!shouldHandleMaskHotkey()) return;
    e.preventDefault();
    const ov = document.getElementById('mask-overlay');
    if (ov) ov.style.opacity = '1';
});

function resetStats() {
    document.getElementById('damage-percent').innerText = '0.00%';
    document.getElementById('mask-area').innerText = '0';
    document.getElementById('image-size').innerText = '- x -';
    document.getElementById('empty-state').style.display = 'flex';
    document.getElementById('image-wrapper').style.display = 'none';
    document.getElementById('hint-text').style.display = 'none';
}

checkLoginState();
syncResultsPanelVisibility();
