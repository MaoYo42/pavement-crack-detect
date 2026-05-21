import asyncio
import json
import os
import subprocess
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import segmentation_models_pytorch as smp
import torch
import torchvision.transforms as transforms
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import auth, models
from .database import DATABASE_PATH, SessionLocal, engine, get_db

models.Base.metadata.create_all(bind=engine)


def _ensure_schema():
    with engine.begin() as conn:
        columns = conn.execute(text("PRAGMA table_info(users)")).fetchall()
        column_names = {row[1] for row in columns}
        if "is_active" not in column_names:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"))


_ensure_schema()

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
RUNTIME_DIR = Path(
    os.getenv(
        "INTERFACE_MACOS_RUNTIME_DIR",
        str(Path.home() / "Library" / "Application Support" / "Interface"),
    )
).expanduser()
OUTPUT_DIR = Path(os.getenv("INTERFACE_MACOS_OUTPUT_DIR", str(RUNTIME_DIR / "outputs"))).expanduser()
STATIC_DIR = APP_DIR / "static"

RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="路面裂缝智能检测分割平台接口 - macOS")

DEFAULT_ALLOW_ORIGINS = "http://127.0.0.1:8000,http://localhost:8000"
ALLOW_ORIGINS = [origin.strip() for origin in os.getenv("ALLOW_ORIGINS", DEFAULT_ALLOW_ORIGINS).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_model_path() -> Optional[Path]:
    candidates = []

    env_model = os.getenv("MODEL_PATH")
    if env_model:
        candidates.append(Path(env_model).expanduser())

    candidates.extend(
        [
            Path.home() / "Documents" / "机器学习实验包" / "U-net 最优weights" / "best_model_pro.pth",
            PROJECT_ROOT.parent / "auto_labeling" / "weights" / "best_model_pro.pth",
            PROJECT_ROOT / "weights" / "best_model_pro.pth",
            RUNTIME_DIR / "weights" / "best_model_pro.pth",
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else None


MODEL_WEIGHTS = _resolve_model_path()
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

preprocess = transforms.Compose(
    [
        transforms.Resize((1024, 1024)),
        transforms.Grayscale(num_output_channels=1),
        transforms.ToTensor(),
        transforms.Normalize(mean=(0.5,), std=(0.5,)),
    ]
)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "30"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def _safe_filename(raw_name: str) -> str:
    name = Path(raw_name or "uploaded_image").name
    safe_chars = []
    for ch in name:
        if ch.isalnum() or ch in (".", "-", "_", " "):
            safe_chars.append(ch)
        else:
            safe_chars.append("_")
    cleaned = "".join(safe_chars).strip("._ ")
    return cleaned or "uploaded_image"


def load_model() -> bool:
    if MODEL_WEIGHTS is None or not MODEL_WEIGHTS.exists():
        print(f"未找到模型权重: {MODEL_WEIGHTS}")
        return False
    try:
        state_dict = torch.load(MODEL_WEIGHTS, map_location=device)
        if isinstance(state_dict, dict):
            for key in ("state_dict", "model_state_dict", "model", "net"):
                if key in state_dict and isinstance(state_dict[key], dict):
                    state_dict = state_dict[key]
                    break
        cleaned_state_dict = {}
        for key, value in state_dict.items():
            clean_key = key.replace("_orig_mod.", "").replace("module.", "")
            cleaned_state_dict[clean_key] = value
        net.load_state_dict(cleaned_state_dict)
        net.to(device)
        net.eval()
        print(f"模型加载成功: {MODEL_WEIGHTS} (设备: {device})")
        return True
    except Exception as exc:
        print(f"模型加载失败: {exc}")
        return False


model_loaded = load_model()


def perform_inference(image_path: Path):
    raw_img = ImageOps.exif_transpose(Image.open(image_path)).convert("L")
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
    mask_area = int(np.sum(mask_np > 0))

    return mask_np, mask_area, total_area, original_width, original_height


def _resolve_output_path(url_path: Optional[str]) -> Optional[Path]:
    if not url_path or not url_path.startswith("/outputs/"):
        return None
    return OUTPUT_DIR / url_path.removeprefix("/outputs/")


def _output_url(path: Path) -> str:
    return f"/outputs/{path.relative_to(OUTPUT_DIR).as_posix()}"


def _build_visualization_assets(
    source_path: Path,
    output_dir: Path,
    original_filename: str,
    mask_np: np.ndarray,
    copy_original: bool = False,
):
    output_dir.mkdir(parents=True, exist_ok=True)
    original_target = output_dir / original_filename
    if copy_original and source_path.resolve() != original_target.resolve():
        shutil.copy2(source_path, original_target)

    source_img = ImageOps.exif_transpose(Image.open(source_path)).convert("RGBA")
    width, height = source_img.size

    transparent_mask = np.zeros((height, width, 4), dtype=np.uint8)
    # PIL RGBA：红色半透明叠加，与前端「红色掩膜叠加层」说明一致
    transparent_mask[mask_np > 0] = [255, 0, 0, 180]

    stem = Path(original_filename).stem
    mask_filename = f"{stem}_mask.png"
    overlay_filename = f"{stem}_overlay.png"
    mask_path = output_dir / mask_filename
    overlay_path = output_dir / overlay_filename

    mask_image = Image.fromarray(transparent_mask, mode="RGBA")
    mask_image.save(mask_path)

    overlay_image = Image.alpha_composite(source_img, mask_image)
    overlay_image.save(overlay_path)

    return {
        "original_path": original_target,
        "mask_path": mask_path,
        "overlay_path": overlay_path,
    }


def _delete_output_file(url_path: Optional[str]):
    path = _resolve_output_path(url_path)
    if path and path.exists():
        try:
            path.unlink()
        except IsADirectoryError:
            shutil.rmtree(path, ignore_errors=True)


def _parse_query_datetime(value: Optional[str], end_of_day: bool = False) -> Optional[datetime]:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) == 10 and cleaned.count("-") == 2:
        cleaned = f"{cleaned}T23:59:59.999999" if end_of_day else f"{cleaned}T00:00:00"
    else:
        cleaned = cleaned.replace(" ", "T")
    return datetime.fromisoformat(cleaned)



class UserCreate(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 2:
            raise ValueError("用户名至少需要 2 个字符")
        if len(stripped) > 32:
            raise ValueError("用户名不能超过 32 个字符")
        if not stripped.replace("_", "").replace("-", "").isalnum():
            raise ValueError("用户名仅支持字母、数字、下划线和连字符")
        return stripped

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("密码长度至少为 6 位")
        if len(v) > 128:
            raise ValueError("密码长度不能超过 128 位")
        return v


class AdminUserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"
    is_active: bool = True

    @field_validator("username")
    @classmethod
    def validate_admin_username(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 2:
            raise ValueError("用户名至少需要 2 个字符")
        if len(stripped) > 32:
            raise ValueError("用户名不能超过 32 个字符")
        if not stripped.replace("_", "").replace("-", "").isalnum():
            raise ValueError("用户名仅支持字母、数字、下划线和连字符")
        return stripped

    @field_validator("password")
    @classmethod
    def validate_admin_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("密码长度至少为 6 位")
        if len(v) > 128:
            raise ValueError("密码长度不能超过 128 位")
        return v

    @field_validator("role")
    @classmethod
    def validate_admin_role(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {"user", "admin"}:
            raise ValueError("角色必须是 'user' 或 'admin'")
        return v


class AdminUserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


@app.post("/auth/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="用户名已存在")

    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(username=user.username, password_hash=hashed_password, role="user", is_active=True)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    db.add(models.SystemLog(user_id=new_user.id, action="新用户注册"))
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
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已停用")

    access_token = auth.create_access_token(data={"sub": user.username, "role": user.role})
    db.add(models.SystemLog(user_id=user.id, action="用户登录"))
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
    }


@app.get("/history/detail/{task_id}")
def get_history_detail(task_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    task = db.query(models.DetectionTask).filter(models.DetectionTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="记录不存在")
    if task.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权查看该记录")

    result = task.result
    return {
        "task_id": task.id,
        "user": task.user.username if task.user else "Unknown",
        "image_path": task.image_path,
        "mask_path": result.mask_path if result else None,
        "overlay_path": result.overlay_path if result else None,
        "status": task.status,
        "duration_ms": task.duration_ms,
        "created_at": task.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "score": result.score if result else None,
    }


@app.post("/predict/")
async def predict(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if not model_loaded:
        return JSONResponse({"status": "error", "message": "模型尚未加载，请检查后端权重文件。"}, status_code=500)

    start_time = time.time()
    task = None
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = _safe_filename(file.filename)
        suffix = Path(safe_name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            return JSONResponse({"status": "error", "message": "仅支持 jpg/jpeg/png 图片格式。"}, status_code=400)

        input_filename = f"orig_{timestamp}_{safe_name}"
        input_path = OUTPUT_DIR / input_filename

        file_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            return JSONResponse({"status": "error", "message": f"上传限制为 {MAX_UPLOAD_MB}MB。"}, status_code=413)

        input_path.write_bytes(file_bytes)

        task = models.DetectionTask(
            user_id=current_user.id,
            image_path=f"/outputs/{input_filename}",
            status="处理中",
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        mask_np, mask_area, total_area, width, height = perform_inference(input_path)
        assets = _build_visualization_assets(input_path, OUTPUT_DIR, input_filename, mask_np)

        damage_percent = (mask_area / total_area) * 100 if total_area > 0 else 0
        duration_ms = (time.time() - start_time) * 1000

        task.status = "已完成"
        task.duration_ms = duration_ms
        db.add(task)

        result = models.DetectionResult(
            task_id=task.id,
            mask_path=_output_url(assets["mask_path"]),
            overlay_path=_output_url(assets["overlay_path"]),
            score=damage_percent,
        )
        db.add(result)
        db.add(models.SystemLog(user_id=current_user.id, action=f"执行单图推理: {safe_name}"))
        db.commit()

        return JSONResponse(
            {
                "status": "success",
                "original_url": f"/outputs/{input_filename}",
                "mask_url": _output_url(assets["mask_path"]),
                "overlay_url": _output_url(assets["overlay_path"]),
                "image_height": height,
                "image_width": width,
                "total_area": total_area,
                "mask_area": mask_area,
                "overall_damage_percent": damage_percent,
            }
        )
    except UnidentifiedImageError:
        if task is not None:
            task.status = "失败"
            db.add(task)
            db.commit()
        return JSONResponse({"status": "error", "message": "上传文件不是有效图像。"}, status_code=400)
    except Exception as exc:
        if task is not None:
            task.status = "失败"
            db.add(task)
            db.commit()
        import traceback

        traceback.print_exc()
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=500)


@app.get("/predict_batch_stream/")
async def predict_batch_stream(
    folder_path: str = Query(..., description="本地文件夹绝对路径"),
    token: str = Query("", description="前端手动传入的JWT授权码"),
    db: Session = Depends(get_db),
):
    import jwt

    if not (token or "").strip():
        return StreamingResponse(
            iter([f"data: {json.dumps({'event': 'error', 'message': '请先登录后再启动批处理'})}\n\n"]),
            media_type="text/event-stream; charset=utf-8",
        )

    try:
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise ValueError()
        current_user = db.query(models.User).filter(models.User.username == username).first()
        if not current_user or not current_user.is_active:
            raise ValueError()
    except Exception:
        return StreamingResponse(
            iter([f"data: {json.dumps({'event': 'error', 'message': '权限凭证无效'})}\n\n"]),
            media_type="text/event-stream; charset=utf-8",
        )

    user_id = current_user.id

    if not model_loaded:
        payload = {"event": "error", "message": "模型尚未加载"}
        return StreamingResponse(iter([f"data: {json.dumps(payload)}\n\n"]), media_type="text/event-stream; charset=utf-8")

    folder = Path(folder_path).expanduser()
    try:
        folder_resolved = folder.resolve()
    except OSError:
        folder_resolved = folder

    if not folder_resolved.exists() or not folder_resolved.is_dir():
        payload = {"event": "error", "message": "路径不存在，或该路径不是文件夹"}
        return StreamingResponse(iter([f"data: {json.dumps(payload)}\n\n"]), media_type="text/event-stream; charset=utf-8")

    db.add(models.SystemLog(user_id=user_id, action=f"启动批量推理: {folder_resolved}"))
    db.commit()

    async def event_generator():
        """流式响应期间使用独立 Session，避免依赖注入的 db 在响应结束后被关闭导致写入失败。"""
        db_batch = SessionLocal()
        original_dir_name = folder_resolved.name
        batch_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        batch_output_dir = OUTPUT_DIR / "batch" / f"{original_dir_name}_{batch_stamp}_MASK"

        try:
            try:
                batch_output_dir.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                yield f"data: {json.dumps({'event': 'error', 'message': f'创建输出目录失败: {exc}'})}\n\n"
                return

            images = [
                path
                for path in folder_resolved.rglob("*")
                if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS
            ]

            if not images:
                yield f"data: {json.dumps({'event': 'error', 'message': '所选目录中未找到可处理的图片文件'})}\n\n"
                return

            total = len(images)
            yield f"data: {json.dumps({'event': 'start', 'total': total, 'batch_dir': str(batch_output_dir)})}\n\n"

            for idx, img_path in enumerate(images, start=1):
                committed_task_id: Optional[int] = None
                image_start = time.time()
                base_name = img_path.name
                try:
                    mask_np, mask_area, total_area, _, _ = await asyncio.to_thread(perform_inference, img_path)
                    try:
                        rel_path = Path(os.path.relpath(img_path, folder_resolved))
                    except ValueError:
                        rel_path = Path(base_name)

                    asset_dir = batch_output_dir / rel_path.parent
                    assets = await asyncio.to_thread(
                        _build_visualization_assets,
                        img_path,
                        asset_dir,
                        rel_path.name,
                        mask_np,
                        True,
                    )

                    task = models.DetectionTask(
                        user_id=user_id,
                        image_path=f"/outputs/batch/{original_dir_name}_{batch_stamp}_MASK/{rel_path.as_posix()}",
                        status="处理中",
                    )
                    db_batch.add(task)
                    db_batch.commit()
                    db_batch.refresh(task)
                    committed_task_id = task.id

                    damage_percent = (mask_area / total_area) * 100 if total_area > 0 else 0
                    duration_ms = (time.time() - image_start) * 1000
                    task.status = "已完成"
                    task.duration_ms = duration_ms
                    db_batch.add(task)

                    result = models.DetectionResult(
                        task_id=task.id,
                        mask_path=_output_url(assets["mask_path"]),
                        overlay_path=_output_url(assets["overlay_path"]),
                        score=damage_percent,
                    )
                    db_batch.add(result)
                    db_batch.add(models.SystemLog(user_id=user_id, action=f"执行批量推理: {base_name}"))
                    db_batch.commit()

                    payload = {
                        "event": "progress",
                        "current": idx,
                        "total": total,
                        "file": base_name,
                        "damage_percent": damage_percent,
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                except Exception as exc:
                    if committed_task_id is not None:
                        try:
                            db_batch.rollback()
                            t = (
                                db_batch.query(models.DetectionTask)
                                .filter(models.DetectionTask.id == committed_task_id)
                                .first()
                            )
                            if t is not None:
                                t.status = "失败"
                                t.duration_ms = (time.time() - image_start) * 1000
                                db_batch.add(
                                    models.SystemLog(user_id=user_id, action=f"批量推理失败: {base_name}")
                                )
                                db_batch.commit()
                        except Exception:
                            db_batch.rollback()
                    yield f"data: {json.dumps({'event': 'file_error', 'file': base_name, 'message': str(exc)})}\n\n"
                await asyncio.sleep(0.01)

            yield f"data: {json.dumps({'event': 'done', 'total': total})}\n\n"
        finally:
            db_batch.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/history/me")
def get_my_history(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    query = db.query(models.DetectionTask).filter(models.DetectionTask.user_id == current_user.id)
    start_dt = _parse_query_datetime(start_date)
    end_dt = _parse_query_datetime(end_date, end_of_day=True)
    if start_dt:
        query = query.filter(models.DetectionTask.created_at >= start_dt)
    if end_dt:
        query = query.filter(models.DetectionTask.created_at <= end_dt)
    if status and status not in {"", "all"}:
        query = query.filter(models.DetectionTask.status == status)

    tasks = query.order_by(models.DetectionTask.created_at.desc()).all()
    history = []
    for t in tasks:
        result = t.result
        history.append(
            {
                "task_id": t.id,
                "image_path": t.image_path,
                "status": t.status,
                "duration_ms": t.duration_ms,
                "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "mask_path": result.mask_path if result else None,
                "overlay_path": result.overlay_path if result else None,
                "score": result.score if result else None,
            }
        )
    return {"history": history}


def _serialize_user(user: models.User):
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "created": user.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/admin/users")
def get_all_users(db: Session = Depends(get_db), admin: models.User = Depends(auth.get_current_admin_user)):
    users = db.query(models.User).order_by(models.User.created_at.desc()).all()
    return {"users": [_serialize_user(u) for u in users]}


@app.post("/admin/users")
def create_admin_user(payload: AdminUserCreate, db: Session = Depends(get_db), admin: models.User = Depends(auth.get_current_admin_user)):
    role = payload.role.strip().lower()
    if role not in {"user", "admin"}:
        raise HTTPException(status_code=400, detail="角色参数无效")
    if db.query(models.User).filter(models.User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = models.User(
        username=payload.username,
        password_hash=auth.get_password_hash(payload.password),
        role=role,
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(models.SystemLog(user_id=admin.id, action=f"管理员创建用户: {user.username}"))
    db.commit()
    return {"message": "用户创建成功", "user": _serialize_user(user)}


@app.put("/admin/users/{user_id}")
def update_admin_user(
    user_id: int,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_admin_user),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if payload.username:
        duplicate = db.query(models.User).filter(models.User.username == payload.username, models.User.id != user_id).first()
        if duplicate:
            raise HTTPException(status_code=400, detail="用户名已存在")
        user.username = payload.username

    if payload.password:
        user.password_hash = auth.get_password_hash(payload.password)

    if payload.role:
        role = payload.role.strip().lower()
        if role not in {"user", "admin"}:
            raise HTTPException(status_code=400, detail="角色参数无效")
        if user.id == admin.id and role != "admin":
            raise HTTPException(status_code=400, detail="不能修改自己的管理员权限")
        if user.role == "admin" and role != "admin":
            active_admins = db.query(models.User).filter(models.User.role == "admin", models.User.is_active == True).count()
            if active_admins <= 1:
                raise HTTPException(status_code=400, detail="至少保留一个管理员账号")
        user.role = role

    if payload.is_active is not None:
        if user.id == admin.id and payload.is_active is False:
            raise HTTPException(status_code=400, detail="不能停用自己的账号")
        user.is_active = payload.is_active

    db.add(user)
    db.add(models.SystemLog(user_id=admin.id, action=f"管理员修改用户: {user.username}"))
    db.commit()
    db.refresh(user)
    return {"message": "用户更新成功", "user": _serialize_user(user)}


@app.patch("/admin/users/{user_id}/disable")
def disable_admin_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_admin_user),
):
    return update_admin_user(user_id, AdminUserUpdate(is_active=False), db=db, admin=admin)


@app.patch("/admin/users/{user_id}/enable")
def enable_admin_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_admin_user),
):
    return update_admin_user(user_id, AdminUserUpdate(is_active=True), db=db, admin=admin)


@app.delete("/admin/users/{user_id}")
def delete_admin_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_admin_user),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")
    if user.role == "admin":
        active_admins = db.query(models.User).filter(models.User.role == "admin", models.User.is_active == True).count()
        if active_admins <= 1:
            raise HTTPException(status_code=400, detail="至少保留一个管理员账号")

    tasks = db.query(models.DetectionTask).filter(models.DetectionTask.user_id == user.id).all()
    logs = db.query(models.SystemLog).filter(models.SystemLog.user_id == user.id).all()
    for task in tasks:
        if task.result:
            _delete_output_file(task.result.mask_path)
            _delete_output_file(task.result.overlay_path)
            db.delete(task.result)
        _delete_output_file(task.image_path)
        db.delete(task)
    for log in logs:
        db.delete(log)
    db.delete(user)
    db.add(models.SystemLog(user_id=admin.id, action=f"管理员删除用户: {user.username}"))
    db.commit()
    return {"message": "用户删除成功"}


@app.get("/admin/tasks")
def get_all_tasks(db: Session = Depends(get_db), admin: models.User = Depends(auth.get_current_admin_user)):
    tasks = db.query(models.DetectionTask).order_by(models.DetectionTask.created_at.desc()).all()
    data = []
    for t in tasks:
        username = t.user.username if t.user else "Unknown"
        data.append(
            {
                "task_id": t.id,
                "user": username,
                "image_path": t.image_path,
                "status": t.status,
                "duration_ms": t.duration_ms,
                "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return {"tasks": data}


@app.delete("/admin/tasks/{task_id}")
def delete_admin_task(
    task_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(auth.get_current_admin_user),
):
    task = db.query(models.DetectionTask).filter(models.DetectionTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.result:
        _delete_output_file(task.result.mask_path)
        _delete_output_file(task.result.overlay_path)
        db.delete(task.result)
    _delete_output_file(task.image_path)
    db.delete(task)
    db.add(models.SystemLog(user_id=admin.id, action=f"管理员删除任务: {task_id}"))
    db.commit()
    return {"message": "任务删除成功"}


@app.get("/admin/logs")
def get_all_logs(db: Session = Depends(get_db), admin: models.User = Depends(auth.get_current_admin_user)):
    logs = db.query(models.SystemLog).order_by(models.SystemLog.created_at.desc()).limit(100).all()
    return {
        "logs": [
            {
                "id": l.id,
                "user": l.user.username if l.user else "N/A",
                "action": l.action,
                "time": l.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for l in logs
        ]
    }


@app.get("/admin/system")
def get_system_info(db: Session = Depends(get_db), admin: models.User = Depends(auth.get_current_admin_user)):
    try:
        db.execute(text("SELECT 1"))
        database_status = "正常"
    except Exception:
        database_status = "异常"

    return {
        "model_loaded": model_loaded,
        "model_path": str(MODEL_WEIGHTS) if MODEL_WEIGHTS else None,
        "database_path": str(DATABASE_PATH),
        "database_status": database_status,
        "output_dir": str(OUTPUT_DIR),
        "runtime_dir": str(RUNTIME_DIR),
        "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
        "max_upload_mb": MAX_UPLOAD_MB,
        "device": str(device),
        "allow_origins": ALLOW_ORIGINS,
    }


app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def read_index():
    return FileResponse(STATIC_DIR / "index.html")


def _open_folder_dialog():
    prompt = "请选择图片文件夹"
    if os.name == "posix" and Path("/System/Library/CoreServices/Finder.app").exists():
        try:
            script = f'set chosenFolder to choose folder with prompt "{prompt}"\nPOSIX path of chosenFolder'
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except Exception:
            pass

    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder_path = filedialog.askdirectory(title=prompt)
        root.destroy()
        return folder_path
    except Exception:
        return ""


@app.get("/ask_folder/")
async def ask_folder():
    folder_path = await asyncio.to_thread(_open_folder_dialog)
    return {"path": folder_path}
