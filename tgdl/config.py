import os
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
TGDL_DIR = BASE_DIR / "tgdl"

def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

load_env(BASE_DIR / ".env")

API_ID_RAW = os.environ.get("TELEGRAM_API_ID")
API_ID: Optional[int] = int(API_ID_RAW) if API_ID_RAW and API_ID_RAW.isdigit() else None
API_HASH: Optional[str] = os.environ.get("TELEGRAM_API_HASH")

SESSION_PATH: str = os.environ.get("TELEGRAM_SESSION_PATH", str(TGDL_DIR / "session" / "tgdl.session"))
DATABASE_PATH: str = os.environ.get("DATABASE_PATH", str(TGDL_DIR / "cache" / "tgdl.db"))
DOWNLOAD_DIR: str = os.environ.get("DOWNLOAD_DIR", str(TGDL_DIR / "downloads"))
CONCURRENT_DOWNLOADS: int = int(os.environ.get("CONCURRENT_DOWNLOADS", "2"))

def reload_config() -> None:
    global API_ID, API_HASH, SESSION_PATH, DATABASE_PATH, DOWNLOAD_DIR, CONCURRENT_DOWNLOADS
    load_env(BASE_DIR / ".env")
    raw = os.environ.get("TELEGRAM_API_ID")
    API_ID = int(raw) if raw and raw.isdigit() else None
    API_HASH = os.environ.get("TELEGRAM_API_HASH")
    SESSION_PATH = os.environ.get("TELEGRAM_SESSION_PATH", str(TGDL_DIR / "session" / "tgdl.session"))
    DATABASE_PATH = os.environ.get("DATABASE_PATH", str(TGDL_DIR / "cache" / "tgdl.db"))
    DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", str(TGDL_DIR / "downloads"))
    CONCURRENT_DOWNLOADS = int(os.environ.get("CONCURRENT_DOWNLOADS", "2"))

def is_config_valid() -> bool:
    return API_ID is not None and API_HASH is not None
