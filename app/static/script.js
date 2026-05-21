const tabs = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');

// JWT Cache
let currentToken = localStorage.getItem('token') || null;
let currentRole = localStorage.getItem('role') || 'user';
let currentUsername = localStorage.getItem('username') || '';

// DOM Elements
const authModal = document.getElementById('auth-modal');
const mainDashboard = document.getElementById('main-dashboard');
const userPanel = document.getElementById('user-panel');
const adminTabBtn = document.querySelector('.admin-only');

const authTitle = document.getElementById('auth-title');
const authUser = document.getElementById('auth-username');
const authPass = document.getElementById('auth-password');
const authRole = document.getElementById('auth-role');
let authMode = 'login'; // 'login' or 'register'

// Utils
function fetchWithAuth(url, options = {}) {
    if (currentToken) {
        options.headers = options.headers || {};
        options.headers['Authorization'] = `Bearer ${currentToken}`;
    }
    return fetch(url, options);
}

// ---------------- AUTH FLOW ---------------- //
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
    authTitle.innerText = mode === 'login' ? '系统登录' : '创建新账号';
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
        const role = authRole.value;
        const res = await fetch('/auth/register', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username, password, role})
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

// ---------------- TAB LOGIC ---------------- //
tabs.forEach((tab) => {
    tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        tabContents.forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.querySelector(tab.dataset.target).classList.add('active');
    });
});

// ---------------- SINGLE INFERENCE ---------------- //
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
        document.getElementById('mask-overlay').src = data.mask_url;
        
        document.getElementById('damage-percent').innerText = data.overall_damage_percent.toFixed(2) + '%';
        document.getElementById('mask-area').innerText = data.mask_area;
        document.getElementById('image-size').innerText = `${data.image_width} x ${data.image_height}`;
    } catch (e) {
        alert("推理失败: " + e.message);
    } finally {
        loader.classList.remove('active');
    }
});

// ---------------- BATCH INFERENCE ---------------- //
let batchSource = null;
const batchStartBtn = document.getElementById('batch-start-btn');
const folderInput = document.getElementById('folder-path');

document.getElementById('browse-btn').addEventListener('click', async () => {
    try {
        const res = await fetchWithAuth('/ask_folder/');
        const data = await res.json();
        if (data.path) folderInput.value = data.path.replace(/\//g, '\\');
    } catch (e) { alert("获取文件路径失败，请手动输入"); }
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

// ---------------- HISTORY & ADMIN PANEL ---------------- //
async function fetchMyHistory() {
    const res = await fetchWithAuth('/history/me');
    if (!res.ok) return;
    const data = await res.json();
    let html = `<table><tr><th>时间</th><th>原图路径</th><th>状态</th><th>耗时(ms)</th><th>损伤%</th></tr>`;
    data.history.forEach(h => {
        html += `<tr>
            <td>${h.created_at}</td>
            <td>${h.image_path}</td>
            <td>${h.status}</td>
            <td>${h.duration_ms ? h.duration_ms.toFixed(0) : '-'}</td>
            <td>${h.score ? h.score.toFixed(2) : '-'}</td>
        </tr>`;
    });
    html += `</table>`;
    document.getElementById('history-container').innerHTML = html;
}

const adminSubTabBtns = document.querySelectorAll('.admin-subtab-btn');
async function switchAdminSubtab(type) {
    adminSubTabBtns.forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    const container = document.getElementById('admin-data-container');
    container.innerHTML = '<p style="padding:1rem;">载入中...</p>';
    
    try {
        const res = await fetchWithAuth(`/admin/${type}`);
        const data = await res.json();
        let html = '<table>';
        if (type === 'users') {
            html += `<tr><th>用户ID</th><th>账号名</th><th>角色</th><th>注册时间</th></tr>`;
            data.users.forEach(u => html += `<tr><td>${u.id}</td><td>${u.username}</td><td>${u.role}</td><td>${u.created}</td></tr>`);
        } else if (type === 'tasks') {
            html += `<tr><th>任务ID</th><th>发起人</th><th>图像路径</th><th>状态</th><th>处理时间</th></tr>`;
            data.tasks.forEach(t => html += `<tr><td>${t.task_id}</td><td>${t.user}</td><td>${t.image_path}</td><td>${t.status}</td><td>${t.created_at}</td></tr>`);
        } else if (type === 'logs') {
            html += `<tr><th>日志ID</th><th>操作人</th><th>行为描述</th><th>操作时间</th></tr>`;
            data.logs.forEach(l => html += `<tr><td>${l.id}</td><td>${l.user}</td><td>${l.action}</td><td>${l.time}</td></tr>`);
        }
        html += '</table>';
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<p style="padding:1rem; color:red;">权限阻断或加载失败</p>`;
    }
}

async function fetchAdminData() {
    switchAdminSubtab('users');
}

// ---------------- HOTKEYS & MISC ---------------- //
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

// Boot
checkLoginState();
