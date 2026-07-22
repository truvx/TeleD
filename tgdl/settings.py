import os
from typing import Any, Optional
from tgdl.constants import (
    DEFAULT_SESSION_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_DOWNLOAD_DIR,
    DEFAULT_CONCURRENT_DOWNLOADS,
    THEME_DARK
)
import tgdl.database as db

class SettingsManager:
    """Manages application settings with persistent DB storage and environment fallbacks."""

    @staticmethod
    async def get(key: str, default: Any = None) -> Any:
        """Retrieve a setting value asynchronously from DB or environment."""
        val = await db.get_setting(key, "")
        if val:
            return val
            
        env_key = f"TELED_{key.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            return env_val
            
        return default

    @staticmethod
    async def set(key: str, value: Any) -> None:
        """Set and persist a setting value in SQLite."""
        await db.set_setting(key, str(value))

    @property
    def session_path(self) -> str:
        return os.environ.get("TELEGRAM_SESSION_PATH", DEFAULT_SESSION_PATH)

    @property
    def database_path(self) -> str:
        return os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH)

    @property
    def download_dir(self) -> str:
        return os.environ.get("DOWNLOAD_DIR", DEFAULT_DOWNLOAD_DIR)

    @property
    def concurrent_downloads(self) -> int:
        raw = os.environ.get("CONCURRENT_DOWNLOADS", str(DEFAULT_CONCURRENT_DOWNLOADS))
        return int(raw) if raw.isdigit() else DEFAULT_CONCURRENT_DOWNLOADS
