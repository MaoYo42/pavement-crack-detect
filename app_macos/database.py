from pathlib import Path
import os

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool


def _get_runtime_db_path() -> Path:
    explicit_db_path = os.getenv("INTERFACE_MACOS_DB_PATH")
    if explicit_db_path:
        db_path = Path(explicit_db_path).expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return db_path

    base_dir = Path(
        os.getenv(
            "INTERFACE_MACOS_RUNTIME_DIR",
            str(Path.home() / "Library" / "Application Support" / "Interface"),
        )
    ).expanduser()
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "crack_detection_macos.db"


DATABASE_PATH = _get_runtime_db_path()
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
