import sqlite3
import os
import asyncio
from typing import List, Optional
from tgdl.config import DATABASE_PATH
from tgdl.models import MessageMetadata

def _init_db_sync() -> None:
    db_dir = os.path.dirname(DATABASE_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id INTEGER PRIMARY KEY,
                filename TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                mime_type TEXT NOT NULL,
                upload_date TEXT NOT NULL,
                download_status TEXT NOT NULL,
                downloaded_bytes INTEGER DEFAULT 0,
                path TEXT
            )
        """)
        conn.commit()

async def init_db() -> None:
    """Initialize the SQLite database schema."""
    await asyncio.to_thread(_init_db_sync)

def _cache_messages_sync(messages: List[MessageMetadata]) -> None:
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.executemany("""
            INSERT OR REPLACE INTO messages 
            (message_id, filename, file_size, mime_type, upload_date, download_status, downloaded_bytes, path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                m.message_id,
                m.filename,
                m.file_size,
                m.mime_type,
                m.upload_date,
                m.download_status,
                m.downloaded_bytes,
                m.path
            )
            for m in messages
        ])
        conn.commit()

async def cache_messages(messages: List[MessageMetadata]) -> None:
    """Batch cache messages to SQLite."""
    if not messages:
        return
    await asyncio.to_thread(_cache_messages_sync, messages)

def _get_cached_messages_sync(
    search_query: Optional[str] = None,
    sort_by: str = "message_id",
    sort_desc: bool = True
) -> List[MessageMetadata]:
    # Validate sort column to avoid SQL injection
    valid_cols = {"message_id", "filename", "file_size", "upload_date", "download_status"}
    if sort_by not in valid_cols:
        sort_by = "message_id"
    
    direction = "DESC" if sort_desc else "ASC"
    query = "SELECT message_id, filename, file_size, mime_type, upload_date, download_status, downloaded_bytes, path FROM messages"
    params = []
    
    if search_query:
        query += " WHERE filename LIKE ? OR mime_type LIKE ?"
        term = f"%{search_query}%"
        params = [term, term]
        
    query += f" ORDER BY {sort_by} {direction}"
    
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        
    return [
        MessageMetadata(
            message_id=row["message_id"],
            filename=row["filename"],
            file_size=row["file_size"],
            mime_type=row["mime_type"],
            upload_date=row["upload_date"],
            download_status=row["download_status"],
            downloaded_bytes=row["downloaded_bytes"],
            path=row["path"]
        )
        for row in rows
    ]

async def get_cached_messages(
    search_query: Optional[str] = None,
    sort_by: str = "message_id",
    sort_desc: bool = True
) -> List[MessageMetadata]:
    """Retrieve filtered and sorted messages from cache."""
    return await asyncio.to_thread(_get_cached_messages_sync, search_query, sort_by, sort_desc)

def _update_download_status_sync(
    message_id: int,
    status: str,
    downloaded_bytes: int,
    path: Optional[str] = None
) -> None:
    with sqlite3.connect(DATABASE_PATH) as conn:
        if path is not None:
            conn.execute(
                "UPDATE messages SET download_status = ?, downloaded_bytes = ?, path = ? WHERE message_id = ?",
                (status, downloaded_bytes, path, message_id)
            )
        else:
            conn.execute(
                "UPDATE messages SET download_status = ?, downloaded_bytes = ? WHERE message_id = ?",
                (status, downloaded_bytes, message_id)
            )
        conn.commit()

async def update_download_status(
    message_id: int,
    status: str,
    downloaded_bytes: int,
    path: Optional[str] = None
) -> None:
    """Update status, downloaded bytes and storage path for a message."""
    await asyncio.to_thread(_update_download_status_sync, message_id, status, downloaded_bytes, path)

def _get_max_message_id_sync() -> int:
    with sqlite3.connect(DATABASE_PATH) as conn:
        row = conn.execute("SELECT MAX(message_id) FROM messages").fetchone()
        return row[0] if row and row[0] is not None else 0

async def get_max_message_id() -> int:
    """Get the highest cached message ID."""
    return await asyncio.to_thread(_get_max_message_id_sync)

def _get_message_sync(message_id: int) -> Optional[MessageMetadata]:
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT message_id, filename, file_size, mime_type, upload_date, download_status, downloaded_bytes, path FROM messages WHERE message_id = ?",
            (message_id,)
        ).fetchone()
        if not row:
            return None
        return MessageMetadata(
            message_id=row["message_id"],
            filename=row["filename"],
            file_size=row["file_size"],
            mime_type=row["mime_type"],
            upload_date=row["upload_date"],
            download_status=row["download_status"],
            downloaded_bytes=row["downloaded_bytes"],
            path=row["path"]
        )

async def get_message(message_id: int) -> Optional[MessageMetadata]:
    """Retrieve metadata for a specific message by its ID."""
    return await asyncio.to_thread(_get_message_sync, message_id)

def _clear_cache_sync() -> None:
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute("DELETE FROM messages")
        conn.commit()

async def clear_cache() -> None:
    """Delete all cached messages."""
    await asyncio.to_thread(_clear_cache_sync)
