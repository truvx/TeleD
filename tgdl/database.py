import sqlite3
import os
import asyncio
from datetime import datetime
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
                extension TEXT NOT NULL DEFAULT '',
                file_size INTEGER NOT NULL,
                mime_type TEXT NOT NULL,
                upload_date TEXT NOT NULL,
                download_status TEXT NOT NULL,
                downloaded_bytes INTEGER DEFAULT 0,
                path TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS download_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                completed_at TEXT NOT NULL,
                path TEXT NOT NULL
            )
        """)
        cursor = conn.execute("PRAGMA table_info(messages)")
        cols = [row[1] for row in cursor.fetchall()]
        if "extension" not in cols:
            conn.execute("ALTER TABLE messages ADD COLUMN extension TEXT NOT NULL DEFAULT ''")
        conn.commit()

async def init_db() -> None:
    await asyncio.to_thread(_init_db_sync)

def _cache_messages_sync(messages: List[MessageMetadata]) -> None:
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.executemany("""
            INSERT OR REPLACE INTO messages 
            (message_id, filename, extension, file_size, mime_type, upload_date, download_status, downloaded_bytes, path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                m.message_id,
                m.filename,
                m.extension,
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
    if not messages:
        return
    await asyncio.to_thread(_cache_messages_sync, messages)

def _get_cached_messages_sync(
    search_query: Optional[str] = None,
    sort_by: str = "message_id",
    sort_desc: bool = True
) -> List[MessageMetadata]:
    valid_cols = {
        "message_id": "message_id",
        "id": "message_id",
        "name": "filename",
        "filename": "filename",
        "size": "file_size",
        "file_size": "file_size",
        "date": "upload_date",
        "upload_date": "upload_date",
        "ext": "extension",
        "extension": "extension"
    }
    col_name = valid_cols.get(sort_by.lower(), "message_id")
    direction = "DESC" if sort_desc else "ASC"
    
    query = "SELECT message_id, filename, extension, file_size, mime_type, upload_date, download_status, downloaded_bytes, path FROM messages"
    params = []
    
    if search_query:
        q = search_query.strip()
        # Handle wildcard queries (*.mkv -> %.mkv, test? -> test_)
        if "*" in q or "?" in q:
            pattern = q.replace("*", "%").replace("?", "_")
        else:
            pattern = f"%{q}%"
            
        query += " WHERE filename LIKE ? OR extension LIKE ? OR upload_date LIKE ? OR mime_type LIKE ?"
        params = [pattern, pattern, pattern, pattern]
        
    query += f" ORDER BY {col_name} {direction}"
    
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        
    return [
        MessageMetadata(
            message_id=row["message_id"],
            filename=row["filename"],
            extension=row["extension"],
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
    await asyncio.to_thread(_update_download_status_sync, message_id, status, downloaded_bytes, path)

def _record_download_history_sync(message_id: int, filename: str, file_size: int, path: str) -> None:
    with sqlite3.connect(DATABASE_PATH) as conn:
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO download_history (message_id, filename, file_size, completed_at, path) VALUES (?, ?, ?, ?, ?)",
            (message_id, filename, file_size, now, path)
        )
        conn.commit()

async def record_download_history(message_id: int, filename: str, file_size: int, path: str) -> None:
    await asyncio.to_thread(_record_download_history_sync, message_id, filename, file_size, path)

def _get_max_message_id_sync() -> int:
    with sqlite3.connect(DATABASE_PATH) as conn:
        row = conn.execute("SELECT MAX(message_id) FROM messages").fetchone()
        return row[0] if row and row[0] is not None else 0

async def get_max_message_id() -> int:
    return await asyncio.to_thread(_get_max_message_id_sync)

def _get_message_sync(message_id: int) -> Optional[MessageMetadata]:
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT message_id, filename, extension, file_size, mime_type, upload_date, download_status, downloaded_bytes, path FROM messages WHERE message_id = ?",
            (message_id,)
        ).fetchone()
        if not row:
            return None
        return MessageMetadata(
            message_id=row["message_id"],
            filename=row["filename"],
            extension=row["extension"],
            file_size=row["file_size"],
            mime_type=row["mime_type"],
            upload_date=row["upload_date"],
            download_status=row["download_status"],
            downloaded_bytes=row["downloaded_bytes"],
            path=row["path"]
        )

async def get_message(message_id: int) -> Optional[MessageMetadata]:
    return await asyncio.to_thread(_get_message_sync, message_id)

def _clear_cache_sync() -> None:
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM download_history")
        conn.commit()

async def clear_cache() -> None:
    await asyncio.to_thread(_clear_cache_sync)
