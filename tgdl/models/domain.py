from dataclasses import dataclass
from typing import Optional

@dataclass
class MessageMetadata:
    message_id: int
    filename: str
    extension: str
    file_size: int
    mime_type: str
    upload_date: str
    download_status: str = "pending"
    downloaded_bytes: int = 0
    chat_id: int = 0
    path: Optional[str] = None
    file_hash: Optional[str] = None
    duration: Optional[int] = None
    resolution: Optional[str] = None

@dataclass
class DownloadJob:
    message_id: int
    filename: str
    file_size: int
    downloaded_bytes: int = 0
    status: str = "pending"
    speed: float = 0.0          # Current speed (B/s)
    avg_speed: float = 0.0      # Average EWMA speed (B/s)
    eta: float = 0.0            # ETA seconds remaining
    progress: float = 0.0       # 0.0 to 100.0
    retries: int = 0
    max_retries: int = 5
    error_msg: Optional[str] = None
