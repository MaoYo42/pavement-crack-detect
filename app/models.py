from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(String, default="user")  # 'admin' or 'user'
    created_at = Column(DateTime, default=datetime.utcnow)

    tasks = relationship("DetectionTask", back_populates="user")
    logs = relationship("SystemLog", back_populates="user")

class DetectionTask(Base):
    __tablename__ = "detection_tasks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    image_path = Column(String) # 原图路径/文件名
    status = Column(String, default="pending") # pending, processing, completed, failed
    duration_ms = Column(Float, nullable=True) # 推理耗时
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="tasks")
    result = relationship("DetectionResult", back_populates="task", uselist=False)

class DetectionResult(Base):
    __tablename__ = "detection_results"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("detection_tasks.id"))
    mask_path = Column(String, nullable=True)
    overlay_path = Column(String, nullable=True)
    score = Column(Float, nullable=True) # 可以存储损伤比(damage_percent)

    task = relationship("DetectionTask", back_populates="result")

class SystemLog(Base):
    __tablename__ = "system_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="logs")
