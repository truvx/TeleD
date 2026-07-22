from pathlib import Path

# Application Metadata
APP_NAME = "TeleD"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "Terminal UI Telegram Downloader"

# Base Directory Resolution
BASE_DIR = Path(__file__).resolve().parent.parent
TGDL_DIR = BASE_DIR / "tgdl"

# Directory Paths
DEFAULT_SESSION_DIR = TGDL_DIR / "session"
DEFAULT_CACHE_DIR = TGDL_DIR / "cache"
DEFAULT_DOWNLOAD_DIR = TGDL_DIR / "downloads"

# Default File Locations
DEFAULT_SESSION_PATH = str(DEFAULT_SESSION_DIR / "session")
DEFAULT_DB_PATH = str(DEFAULT_CACHE_DIR / "tgdl.db")
DEFAULT_LOG_PATH = str(DEFAULT_CACHE_DIR / "tgdl.log")

# Download & Queue Constants
DEFAULT_CONCURRENT_DOWNLOADS = 2
CHUNK_ALIGNMENT_BYTES = 4096  # 4KB boundary required by Telegram GetFile API
MAX_DOWNLOAD_RETRIES = 5
PROGRESS_UPDATE_INTERVAL_SEC = 0.5

# Supported UI Themes
THEME_DARK = "textual-dark"
THEME_LIGHT = "textual-light"
