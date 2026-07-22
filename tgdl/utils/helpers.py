import humanize
from typing import Union

def format_bytes(bytes_count: Union[int, float]) -> str:
    """Format bytes count to human-readable string (e.g., 10.5 MB)."""
    return humanize.naturalsize(bytes_count, binary=True)

def format_speed(bytes_per_sec: float) -> str:
    """Format download speed to human-readable string (e.g., 2.3 MiB/s)."""
    return f"{format_bytes(bytes_per_sec)}/s"

def format_eta(seconds: float) -> str:
    """Format ETA in seconds to a structured HH:MM:SS or MM:SS string."""
    if seconds == float("inf") or seconds < 0:
        return "--:--"
    if seconds > 86400:
        return "> 1 day"
    
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
