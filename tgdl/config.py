import os
from pathlib import Path
from typing import Optional

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
TGDL_DIR = BASE_DIR / "tgdl"

# Setup .env parsing (simple custom parser to avoid python-dotenv dependency)
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
                os.environ.setdefault(key.strip(), val.strip())

# Load local environment if it exists
load_env(BASE_DIR / ".env")

# Telegram API Config
API_ID_RAW = os.environ.get("TELEGRAM_API_ID")
API_ID: Optional[int] = int(API_ID_RAW) if API_ID_RAW and API_ID_RAW.isdigit() else None
API_HASH: Optional[str] = os.environ.get("TELEGRAM_API_HASH")

# Paths config
SESSION_PATH: str = os.environ.get("TELEGRAM_SESSION_PATH", str(TGDL_DIR / "session"))
DATABASE_PATH: str = os.environ.get("DATABASE_PATH", str(TGDL_DIR / "cache" / "tgdl.db"))
DOWNLOAD_DIR: str = os.environ.get("DOWNLOAD_DIR", str(TGDL_DIR / "downloads"))

# Queue parameters
CONCURRENT_DOWNLOADS: int = int(os.environ.get("CONCURRENT_DOWNLOADS", "2"))

def is_config_valid() -> bool:
    """Check if the basic API keys are loaded."""
    return API_ID is not None and API_HASH is not None
