import humanize
from typing import Union, Tuple

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

def get_file_type(filename: str, mime_type: str = "") -> str:
    """Return a short clean upper-case extension or file category."""
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].upper()
        if 1 <= len(ext) <= 5:
            return ext
            
    if mime_type:
        if "/" in mime_type:
            sub = mime_type.split("/", 1)[-1].upper()
            if "JPEG" in sub or "JPG" in sub:
                return "JPG"
            if "PNG" in sub:
                return "PNG"
            if "MP4" in sub or "VIDEO" in sub:
                return "MP4"
            if "PDF" in sub:
                return "PDF"
            if len(sub) <= 5:
                return sub
        if "image" in mime_type:
            return "IMG"
        if "video" in mime_type:
            return "VID"
        if "audio" in mime_type:
            return "AUD"

    return "FILE"

def get_colored_file_badge(filename: str, mime_type: str = "", extension: str = "") -> str:
    """Return Rich formatted colored badge with icon for file type.
    
    Color rules:
      - Video: Blue
      - PDF: Red
      - ZIP / RAR / Archive: Yellow
      - Images: Magenta
      - Audio: Green
      - Default: Cyan
    """
    ext = (extension or "").lstrip(".").upper() or get_file_type(filename, mime_type)
    mime = (mime_type or "").lower()
    fn = (filename or "").lower()
    
    # Video (Blue)
    if ext in ("MP4", "MKV", "AVI", "MOV", "WEBM", "FLV", "VID") or "video" in mime or fn.endswith((".mp4", ".mkv", ".avi", ".mov")):
        return f"[bold blue]🎬 {ext}[/]"
        
    # PDF (Red)
    if ext == "PDF" or "pdf" in mime or fn.endswith(".pdf"):
        return f"[bold red]📄 {ext}[/]"
        
    # ZIP / RAR / Archives (Yellow)
    if ext in ("ZIP", "RAR", "7Z", "TAR", "GZ", "BZ2", "XZ", "ISO") or "compressed" in mime or "zip" in mime or "rar" in mime or fn.endswith((".zip", ".rar", ".7z", ".tar.gz", ".iso")):
        return f"[bold yellow]📦 {ext}[/]"
        
    # Images (Magenta)
    if ext in ("JPG", "JPEG", "PNG", "GIF", "WEBP", "BMP", "SVG", "IMG") or "image" in mime or fn.endswith((".jpg", ".jpeg", ".png", ".gif")):
        return f"[bold magenta]🖼 {ext}[/]"
        
    # Audio (Green)
    if ext in ("MP3", "FLAC", "WAV", "OGG", "M4A", "AAC", "AUD") or "audio" in mime or fn.endswith((".mp3", ".flac", ".wav", ".ogg")):
        return f"[bold green]🎵 {ext}[/]"
        
    # Default (Cyan)
    return f"[bold cyan]📁 {ext}[/]"
