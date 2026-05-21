import importlib
import gc
import os
import sys
import tempfile
import unittest
from pathlib import Path

import httpx


def load_bundle(runtime_dir: Path):
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "outputs").mkdir(parents=True, exist_ok=True)
    os.environ["INTERFACE_MACOS_RUNTIME_DIR"] = str(runtime_dir)
    os.environ["INTERFACE_MACOS_DB_PATH"] = str(runtime_dir / "crack_detection_macos.db")
    os.environ["MODEL_PATH"] = str(runtime_dir / "missing_model.pth")
    os.environ["ALLOW_ORIGINS"] = "http://127.0.0.1:8000"

    for module_name in ["app_macos.database", "app_macos.auth", "app_macos.models", "app_macos.main"]:
        module = sys.modules.get(module_name)
        engine = getattr(module, "engine", None)
        if engine is not None:
            engine.dispose()

    for module_name in ["app_macos.database", "app_macos.auth", "app_macos.models", "app_macos.main"]:
        sys.modules.pop(module_name, None)
    sys.modules.pop("app_macos", None)
    gc.collect()

    main = importlib.import_module("app_macos.main")
    auth = importlib.import_module("app_macos.auth")
    models = importlib.import_module("app_macos.models")
    database = importlib.import_module("app_macos.database")
    return main, auth, models, database


def seed_user(session_factory, models, auth, username, password, role="user", is_active=True):
    db = session_factory()
    try:
        user = models.User(
            username=username,
            password_hash=auth.get_password_hash(password),
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def create_task_with_result(session_factory, models, output_dir: Path, user_id: int):
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / "sample_orig.jpg"
    mask_path = output_dir / "sample_mask.png"
    overlay_path = output_dir / "sample_overlay.png"
    image_path.write_bytes(b"image-bytes")
    mask_path.write_bytes(b"mask-bytes")
    overlay_path.write_bytes(b"overlay-bytes")

    db = session_factory()
    try:
        task = models.DetectionTask(
            user_id=user_id,
            image_path="/outputs/sample_orig.jpg",
            status="已完成",
            duration_ms=123.0,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        result = models.DetectionResult(
            task_id=task.id,
            mask_path="/outputs/sample_mask.png",
            overlay_path="/outputs/sample_overlay.png",
            score=6.78,
        )
        db.add(result)
        db.commit()
        return task.id
    finally:
        db.close()


async def login(client: httpx.AsyncClient, username: str, password: str):
    response = await client.post("/auth/login", data={"username": username, "password": password})
    if response.status_code != 200:
        raise AssertionError(response.text)
    return response.json()["access_token"]


class ManagementAPITest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.runtime_dir = Path(self.tempdir.name) / "runtime"
        self.main, self.auth, self.models, self.database = load_bundle(self.runtime_dir)
        transport = httpx.ASGITransport(app=self.main.app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)

    async def test_system_info_and_user_crud(self):
        seed_user(self.database.SessionLocal, self.models, self.auth, "admin-user", "secret", role="admin")
        token = await login(self.client, "admin-user", "secret")

        system = await self.client.get("/admin/system", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(system.status_code, 200, system.text)
        system_data = system.json()
        self.assertEqual(system_data["database_status"], "正常")
        self.assertEqual(system_data["max_upload_mb"], self.main.MAX_UPLOAD_MB)
        self.assertIn("http://127.0.0.1:8000", system_data["allow_origins"])

        create = await self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            json={"username": "new-user", "password": "pwd123", "role": "user", "is_active": True},
        )
        self.assertEqual(create.status_code, 200, create.text)
        created_id = create.json()["user"]["id"]
        self.assertTrue(create.json()["user"]["is_active"])

        update = await self.client.put(
            f"/admin/users/{created_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"username": "new-user-renamed", "is_active": False},
        )
        self.assertEqual(update.status_code, 200, update.text)
        updated_user = update.json()["user"]
        self.assertEqual(updated_user["username"], "new-user-renamed")
        self.assertEqual(updated_user["role"], "user")
        self.assertFalse(updated_user["is_active"])

        enable = await self.client.patch(
            f"/admin/users/{created_id}/enable",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(enable.status_code, 200, enable.text)
        self.assertTrue(enable.json()["user"]["is_active"])

        disable = await self.client.patch(
            f"/admin/users/{created_id}/disable",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(disable.status_code, 200, disable.text)
        self.assertFalse(disable.json()["user"]["is_active"])

        delete = await self.client.delete(
            f"/admin/users/{created_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(delete.status_code, 200, delete.text)
        self.assertEqual(delete.json()["message"], "用户删除成功")

        db = self.database.SessionLocal()
        try:
            self.assertIsNone(db.query(self.models.User).filter(self.models.User.id == created_id).first())
        finally:
            db.close()

    async def test_task_delete_and_history_detail(self):
        admin = seed_user(self.database.SessionLocal, self.models, self.auth, "admin-two", "secret", role="admin")
        token = await login(self.client, "admin-two", "secret")
        task_id = create_task_with_result(self.database.SessionLocal, self.models, self.main.OUTPUT_DIR, admin.id)

        detail = await self.client.get(
            f"/history/detail/{task_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["task_id"], task_id)
        self.assertEqual(detail.json()["overlay_path"], "/outputs/sample_overlay.png")

        delete = await self.client.delete(
            f"/admin/tasks/{task_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(delete.status_code, 200, delete.text)
        self.assertEqual(delete.json()["message"], "任务删除成功")

        self.assertFalse((self.main.OUTPUT_DIR / "sample_orig.jpg").exists())
        self.assertFalse((self.main.OUTPUT_DIR / "sample_mask.png").exists())
        self.assertFalse((self.main.OUTPUT_DIR / "sample_overlay.png").exists())

        db = self.database.SessionLocal()
        try:
            self.assertIsNone(db.query(self.models.DetectionTask).filter(self.models.DetectionTask.id == task_id).first())
            self.assertIsNone(db.query(self.models.DetectionResult).filter(self.models.DetectionResult.task_id == task_id).first())
        finally:
            db.close()

    async def test_history_filter_and_active_guard(self):
        seed_user(self.database.SessionLocal, self.models, self.auth, "active-admin", "secret", role="admin")
        token = await login(self.client, "active-admin", "secret")

        db = self.database.SessionLocal()
        try:
            user = self.models.User(
                username="inactive-user",
                password_hash=self.auth.get_password_hash("secret"),
                role="user",
                is_active=False,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            task = self.models.DetectionTask(user_id=user.id, image_path="/outputs/inactive.jpg", status="已完成", duration_ms=10)
            db.add(task)
            db.commit()
        finally:
            db.close()

        inactive_login = await self.client.post("/auth/login", data={"username": "inactive-user", "password": "secret"})
        self.assertEqual(inactive_login.status_code, 403)

        history = await self.client.get("/history/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(history.status_code, 200, history.text)
        self.assertIsInstance(history.json()["history"], list)

        filtered = await self.client.get(
            "/history/me",
            headers={"Authorization": f"Bearer {token}"},
            params={"status": "已完成"},
        )
        self.assertEqual(filtered.status_code, 200, filtered.text)
        self.assertTrue(all(item["status"] == "已完成" for item in filtered.json()["history"]))


if __name__ == "__main__":
    unittest.main()
