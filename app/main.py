import asyncio
import glob
import json
import os
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog
import time

import cv2
import numpy as np
import segmentation_models_pytorch as smp
import torch
import torchvision.transforms as transforms
from fastapi import FastAPI, File, Query, UploadFile, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel
from sqlalchemy.orm import Session

# Import our new DB and Auth modules
from .database import engine, get_db
from . import models, auth

# Create DB tables
models.Base.metadata.create_all(bind=engine)

APP_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(APP_DIR)
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
STATIC_DIR = os.path.join(APP_DIR, "static")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app = FastAPI(title="路面裂缝辅助标注平台接口")

DEFAULT_ALLOW_ORIGINS = "http://127.0.0.1:8000,http://localhost:8000"
ALLOW_ORIGINS = [origin.strip() for origin in os.getenv("ALLOW_ORIGINS", DEFAULT_ALLOW_ORIGINS).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(PROJECT_ROOT), "auto_labeling", "weights", "best_model_pro.pth")
MODEL_WEIGHTS = os.getenv("MODEL_PATH", DEFAULT_MODEL_PATH)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
if not torch.cuda.is_available() and getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
    device = torch.device("mps")

net = smp.Unet(
    encoder_name="resnet34",
    encoder_weights=None,
    in_channels=1,
    classes=1,
    activation=None,
)

preprocess = transforms.Compose([
    transforms.Resize((1024, 1024)),
    transforms.Grayscale(num_output_channels=1),
    transforms.ToTensor(),
    transforms.Normalize(mean=(0.5,), std=(0.5,)),
])

def _safe_filename(raw_name: str) -> str:
    name = Path(raw_name or "uploaded_image").name
    safe_chars = []
    for ch in name:
        if ch.isalnum() or ch in (".", "-", "_"):
            safe_chars.append(ch)
        else:
            safe_chars.append("_")
    cleaned = "".join(safe_chars).strip("._")
    return cleaned or "uploaded_image"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "30"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

def load_model() -> bool:
    if not os.path.exists(MODEL_WEIGHTS):
        print(f"未找到模型权重: {MODEL_WEIGHTS}")
        return False
    try:
        state_dict = torch.load(MODEL_WEIGHTS, map_location=device)
        if isinstance(state_dict, dict) and "state_dict" in state_dict:
            state_dict = state_dict["state_dict"]
        cleaned_state_dict = {key.replace("_orig_mod.", ""): value for key, value in state_dict.items()}
        net.load_state_dict(cleaned_state_dict)
        net.to(device)
        net.eval()
        print(f"模型加载成功: {MODEL_WEIGHTS} (设备: {device})")
        return True
    except Exception as exc:
        print(f"模型加载失败: {exc}")
        return False

model_loaded = load_model()

def perform_inference(image_path: str):
    raw_img = Image.open(image_path).convert("L")
    original_width, original_height = raw_img.size
    total_area = original_width * original_height

    img_tensor = preprocess(raw_img).unsqueeze(0).to(device)

    with torch.no_grad():
        output = net(img_tensor)
        probs = torch.sigmoid(output)[0, 0]

    full_mask = probs.cpu().numpy()
    binary_mask = (full_mask > 0.5).astype(np.uint8) * 255

    mask_resized = Image.fromarray(binary_mask).resize((original_width, original_height), resample=Image.NEAREST)
    mask_np = np.array(mask_resized)
    mask_bool = mask_np > 0
    mask_area = int(np.sum(mask_bool))

    return mask_np, mask_area, total_area, original_width, original_height

# --- SCHEMAS ---
class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user" # 'admin' or 'user'

# --- AUTH & USER ROUTERS ---
@app.post("/auth/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(username=user.username, password_hash=hashed_password, role=user.role)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # SYSTEM LOG
    log = models.SystemLog(user_id=new_user.id, action="新用户注册")
    db.add(log)
    db.commit()
    return {"message": "注册成功"}

@app.post("/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_access_token(data={"sub": user.username, "role": user.role})
    
    log = models.SystemLog(user_id=user.id, action="用户登录")
    db.add(log)
    db.commit()

    return {"access_token": access_token, "token_type": "bearer", "role": user.role, "username": user.username}


# --- MAIN INFERENCE ROUTERS ---
@app.post("/predict/")
async def predict(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not model_loaded:
        return JSONResponse({"status": "error", "message": "模型尚未加载，请检查后端权重文件。"}, status_code=500)

    start_time = time.time()
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = _safe_filename(file.filename)
        suffix = Path(safe_name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            return JSONResponse({"status": "error", "message": "仅支持 jpg/jpeg/png 图片格式。"}, status_code=400)

        input_filename = f"orig_{timestamp}_{safe_name}"
        input_path = os.path.join(OUTPUT_DIR, input_filename)

        file_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            return JSONResponse({"status": "error", "message": f"上传限制为 {MAX_UPLOAD_MB}MB。"}, status_code=413)

        with open(input_path, "wb") as buffer:
            buffer.write(file_bytes)

        # 1. 建立识别任务
        task = models.DetectionTask(
            user_id=current_user.id, 
            image_path=f"/outputs/{input_filename}",
            status="处理中"
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        # 推理
        mask_np, mask_area, total_area, width, height = perform_inference(input_path)

        transparent_mask = np.zeros((height, width, 4), dtype=np.uint8)
        transparent_mask[mask_np > 0] = [0, 0, 255, 180]

        mask_filename = f"mask_{timestamp}_{safe_name}.png"
        mask_path = os.path.join(OUTPUT_DIR, mask_filename)
        cv2.imwrite(mask_path, transparent_mask)

        damage_percent = (mask_area / total_area) * 100 if total_area > 0 else 0
        duration_ms = (time.time() - start_time) * 1000

        # 2. 更新任务与创建识别结果
        task.status = "已完成"
        task.duration_ms = duration_ms
        db.add(task)

        result = models.DetectionResult(
            task_id=task.id,
            mask_path=f"/outputs/{mask_filename}",
            overlay_path=f"/outputs/{mask_filename}", # Demo 中叠加图通过前端 CSS 实现，故保存 mask url 作为参考
            score=damage_percent
        )
        db.add(result)
        
        # 3. 日志
        log = models.SystemLog(user_id=current_user.id, action=f"执行单图推理: {safe_name}")
        db.add(log)
        db.commit()

        return JSONResponse({
            "status": "success",
            "original_url": f"/outputs/{input_filename}",
            "mask_url": f"/outputs/{mask_filename}",
            "image_height": height,
            "image_width": width,
            "total_area": total_area,
            "mask_area": mask_area,
            "overall_damage_percent": damage_percent,
        })
    except UnidentifiedImageError:
        return JSONResponse({"status": "error", "message": "上传文件不是有效图像。"}, status_code=400)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)


@app.get("/predict_batch_stream/")
async def predict_batch_stream(
    folder_path: str = Query(..., description="本地文件夹绝对路径"),
    token: str = Query("", description="前端手动传入的JWT授权码"),
    db: Session = Depends(get_db)
):
    import jwt
    from . import auth, models

    if not (token or "").strip():
        return StreamingResponse(
            iter([f"data: {json.dumps({'event': 'error', 'message': '请先登录后再启动批处理'})}\n\n"]),
            media_type="text/event-stream; charset=utf-8",
        )

    try:
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        username = payload.get("sub")
        if not username: raise ValueError()
        current_user = db.query(models.User).filter(models.User.username == username).first()
        if not current_user: raise ValueError()
    except Exception:
        return StreamingResponse(iter([f"data: {json.dumps({'event': 'error', 'message': '权限凭证无效'})}\n\n"]), media_type="text/event-stream; charset=utf-8")

    if not model_loaded:
        payload = {"event": "error", "message": "模型尚未加载"}
        return StreamingResponse(iter([f"data: {json.dumps(payload)}\n\n"]), media_type="text/event-stream; charset=utf-8")

    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        payload = {"event": "error", "message": "路径不存在，或该路径不是文件夹"}
        return StreamingResponse(iter([f"data: {json.dumps(payload)}\n\n"]), media_type="text/event-stream; charset=utf-8")

    # 记录批处理行为
    log = models.SystemLog(user_id=current_user.id, action=f"启动批量推理: {folder_path}")
    db.add(log)
    db.commit()

    async def event_generator():
        original_dir_name = os.path.basename(os.path.normpath(folder_path))
        parent_dir = os.path.dirname(os.path.normpath(folder_path))
        batch_output_dir = os.path.join(parent_dir, f"{original_dir_name}_MASK")

        try:
            os.makedirs(batch_output_dir, exist_ok=True)
        except Exception as exc:
            payload = {"event": "error", "message": f"创建输出目录失败: {exc}"}
            yield f"data: {json.dumps(payload)}\n\n"
            return

        search_exts = ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"]
        images = []
        for ext in search_exts:
            images.extend(glob.glob(os.path.join(folder_path, "**", ext), recursive=True))

        if not images:
            payload = {"event": "error", "message": "所选目录中未找到可处理的图片文件"}
            yield f"data: {json.dumps(payload)}\n\n"
            return

        total = len(images)
        yield f"data: {json.dumps({'event': 'start', 'total': total, 'batch_dir': batch_output_dir})}\n\n"

        for idx, img_path in enumerate(images, start=1):
            try:
                base_name = os.path.basename(img_path)
                mask_np, mask_area, total_area, _, _ = await asyncio.to_thread(perform_inference, img_path)

                save_mask = mask_np.copy()
                save_mask[save_mask > 0] = 255

                rel_path = os.path.relpath(img_path, folder_path)
                rel_mask_path = os.path.splitext(rel_path)[0] + ".png"
                output_path = os.path.join(batch_output_dir, rel_mask_path)
                output_parent = os.path.dirname(output_path)
                if output_parent:
                    os.makedirs(output_parent, exist_ok=True)
                await asyncio.to_thread(cv2.imwrite, output_path, save_mask)

                damage_percent = (mask_area / total_area) * 100 if total_area > 0 else 0
                payload = {
                    "event": "progress",
                    "current": idx,
                    "total": total,
                    "file": base_name,
                    "damage_percent": damage_percent,
                }
                yield f"data: {json.dumps(payload)}\n\n"
            except Exception as exc:
                payload = {"event": "file_error", "file": os.path.basename(img_path), "message": str(exc)}
                yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0.01)
        yield f"data: {json.dumps({'event': 'done', 'total': total})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# --- HISTORY & ADMIN ROUTERS ---
@app.get("/history/me")
def get_my_history(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    tasks = db.query(models.DetectionTask).filter(models.DetectionTask.user_id == current_user.id).order_by(models.DetectionTask.created_at.desc()).all()
    history = []
    for t in tasks:
        result = t.result
        history.append({
            "task_id": t.id,
            "image_path": t.image_path,
            "status": t.status,
            "duration_ms": t.duration_ms,
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "mask_path": result.mask_path if result else None,
            "score": result.score if result else None
        })
    return {"history": history}

@app.get("/admin/users")
def get_all_users(db: Session = Depends(get_db), admin: models.User = Depends(auth.get_current_admin_user)):
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    return {"users": [{"id": u.id, "username": u.username, "role": u.role, "created": u.created_at} for u in users]}

@app.get("/admin/tasks")
def get_all_tasks(db: Session = Depends(get_db), admin: models.User = Depends(auth.get_current_admin_user)):
    tasks = db.query(models.DetectionTask).order_by(models.DetectionTask.created_at.desc()).all()
    data = []
    for t in tasks:
        username = t.user.username if t.user else "Unknown"
        data.append({
            "task_id": t.id,
            "user": username,
            "image_path": t.image_path,
            "status": t.status,
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        })
    return {"tasks": data}

@app.get("/admin/logs")
def get_all_logs(db: Session = Depends(get_db), admin: models.User = Depends(auth.get_current_admin_user)):
    logs = db.query(models.SystemLog).order_by(models.SystemLog.created_at.desc()).limit(100).all()
    return {"logs": [{"id": l.id, "user": l.user.username if l.user else "N/A", "action": l.action, "time": l.created_at.strftime("%Y-%m-%d %H:%M:%S")} for l in logs]}

# --- STATIC FILES ---
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def read_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

def _open_folder_dialog():
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    folder_path = filedialog.askdirectory(title="请选择图片文件夹")
    root.destroy()
    return folder_path

@app.get("/ask_folder/")
async def ask_folder():
    folder_path = await asyncio.to_thread(_open_folder_dialog)
    return {"path": folder_path}
