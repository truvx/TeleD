from dataclasses import dataclass, field
from typing import Optional

@dataclass
class MessageMetadata:
    message_id: int
    filename: str
    file_size: int
    mime_type: str
    upload_date: str
    download_status: str  # 'pending', 'downloading', 'completed', 'failed'
    downloaded_bytes: int = 0
    path: Optional[str] = None

@dataclass
class DownloadJob:
    message_id: int
    filename: str
    file_size: int
    downloaded_bytes: int = 0
    status: str = "pending"  # 'pending', 'downloading', 'completed', 'failed', 'paused'
    speed: float = 0.0      # Bytes per second
    eta: float = 0.0        # Seconds remaining
    progress: float = 0.0   # 0.0 to 100.0
