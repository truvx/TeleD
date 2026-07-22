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
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        conn.execute("PRAGMA cache_size=-64000;")
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                message_id INTEGER PRIMARY KEY,
                filename TEXT NOT NULL,
                extension TEXT NOT NULL DEFAULT '',
                mime_type TEXT NOT NULL,
                size INTEGER NOT NULL,
                date TEXT NOT NULL,
                chat_id INTEGER NOT NULL DEFAULT 0,
                downloaded INTEGER NOT NULL DEFAULT 0,
                local_path TEXT,
                hash TEXT,
                duration INTEGER,
                resolution TEXT
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                size INTEGER NOT NULL,
                downloaded_bytes INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                completed_at TEXT,
                local_path TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        conn.execute("CREATE INDEX IF NOT EXISTS idx_files_filename ON files(filename);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_files_date ON files(date);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_files_size ON files(size);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_files_message_id ON files(message_id);")
        
        # Migrations check
        cursor = conn.execute("PRAGMA table_info(files)")
        cols = [row[1] for row in cursor.fetchall()]
        if "duration" not in cols:
            conn.execute("ALTER TABLE files ADD COLUMN duration INTEGER")
        if "resolution" not in cols:
            conn.execute("ALTER TABLE files ADD COLUMN resolution TEXT")
        conn.commit()

async def init_db() -> None:
    await asyncio.to_thread(_init_db_sync)

def _set_setting_sync(key: str, value: str) -> None:
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()

async def set_setting(key: str, value: str) -> None:
    await asyncio.to_thread(_set_setting_sync, key, value)

def _get_setting_sync(key: str, default: str = "") -> str:
    with sqlite3.connect(DATABASE_PATH) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

async def get_setting(key: str, default: str = "") -> str:
    return await asyncio.to_thread(_get_setting_sync, key, default)

def _cache_messages_sync(messages: List[MessageMetadata]) -> None:
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.executemany("""
            INSERT OR REPLACE INTO files 
            (message_id, filename, extension, mime_type, size, date, chat_id, downloaded, local_path, hash, duration, resolution)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                m.message_id,
                m.filename,
                m.extension,
                m.mime_type,
                m.file_size,
                m.upload_date,
                m.chat_id,
                1 if m.download_status == "completed" else 0,
                m.path,
                m.file_hash,
                m.duration,
                m.resolution
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
    sort_desc: bool = True,
    limit: int = 300,
    offset: int = 0
) -> List[MessageMetadata]:
    valid_cols = {
        "message_id": "message_id", "id": "message_id",
        "name": "filename", "filename": "filename",
        "size": "size", "file_size": "size",
        "date": "date", "upload_date": "date",
        "ext": "extension", "extension": "extension"
    }
    col_name = valid_cols.get(sort_by.lower(), "message_id")
    direction = "DESC" if sort_desc else "ASC"
    
    query = "SELECT message_id, filename, extension, mime_type, size, date, chat_id, downloaded, local_path, hash, duration, resolution FROM files"
    params = []
    
    if search_query:
        q = search_query.strip()
        pattern = q.replace("*", "%").replace("?", "_") if ("*" in q or "?" in q) else f"%{q}%"
        query += " WHERE filename LIKE ? OR extension LIKE ? OR date LIKE ? OR mime_type LIKE ?"
        params = [pattern, pattern, pattern, pattern]
        
    query += f" ORDER BY {col_name} {direction} LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
        
    return [
        MessageMetadata(
            message_id=row["message_id"],
            filename=row["filename"],
            extension=row["extension"],
            file_size=row["size"],
            mime_type=row["mime_type"],
            upload_date=row["date"],
            download_status="completed" if row["downloaded"] == 1 else "pending",
            downloaded_bytes=row["size"] if row["downloaded"] == 1 else 0,
            chat_id=row["chat_id"],
            path=row["local_path"],
            file_hash=row["hash"],
            duration=row["duration"],
            resolution=row["resolution"]
        )
        for row in rows
    ]

async def get_cached_messages(
    search_query: Optional[str] = None,
    sort_by: str = "message_id",
    sort_desc: bool = True,
    limit: int = 300,
    offset: int = 0
) -> List[MessageMetadata]:
    return await asyncio.to_thread(_get_cached_messages_sync, search_query, sort_by, sort_desc, limit, offset)

def _update_download_status_sync(message_id: int, status: str, downloaded_bytes: int, path: Optional[str] = None) -> None:
    with sqlite3.connect(DATABASE_PATH) as conn:
        is_dl = 1 if status == "completed" else 0
        if path is not None:
            conn.execute("UPDATE files SET downloaded = ?, local_path = ? WHERE message_id = ?", (is_dl, path, message_id))
        else:
            conn.execute("UPDATE files SET downloaded = ? WHERE message_id = ?", (is_dl, message_id))
            
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO downloads (message_id, filename, size, downloaded_bytes, status, completed_at, local_path) SELECT message_id, filename, size, ?, ?, ?, ? FROM files WHERE message_id = ?",
            (downloaded_bytes, status, now, path or "", message_id)
        )
        conn.commit()

async def update_download_status(message_id: int, status: str, downloaded_bytes: int, path: Optional[str] = None) -> None:
    await asyncio.to_thread(_update_download_status_sync, message_id, status, downloaded_bytes, path)

def _delete_cached_message_sync(message_id: int) -> None:
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute("DELETE FROM files WHERE message_id = ?", (message_id,))
        conn.execute("DELETE FROM downloads WHERE message_id = ?", (message_id,))
        conn.commit()

async def delete_cached_message(message_id: int) -> None:
    await asyncio.to_thread(_delete_cached_message_sync, message_id)

def _get_max_message_id_sync() -> int:
    with sqlite3.connect(DATABASE_PATH) as conn:
        row = conn.execute("SELECT MAX(message_id) FROM files").fetchone()
        return row[0] if row and row[0] is not None else 0

async def get_max_message_id() -> int:
    return await asyncio.to_thread(_get_max_message_id_sync)

def _get_message_sync(message_id: int) -> Optional[MessageMetadata]:
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT message_id, filename, extension, mime_type, size, date, chat_id, downloaded, local_path, hash, duration, resolution FROM files WHERE message_id = ?", (message_id,)).fetchone()
        if not row:
            return None
        return MessageMetadata(
            message_id=row["message_id"],
            filename=row["filename"],
            extension=row["extension"],
            file_size=row["size"],
            mime_type=row["mime_type"],
            upload_date=row["date"],
            download_status="completed" if row["downloaded"] == 1 else "pending",
            downloaded_bytes=row["size"] if row["downloaded"] == 1 else 0,
            chat_id=row["chat_id"],
            path=row["local_path"],
            file_hash=row["hash"],
            duration=row["duration"],
            resolution=row["resolution"]
        )

async def get_message(message_id: int) -> Optional[MessageMetadata]:
    return await asyncio.to_thread(_get_message_sync, message_id)

def _clear_cache_sync() -> None:
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute("DELETE FROM files")
        conn.execute("DELETE FROM downloads")
        conn.execute("DELETE FROM settings")
        conn.commit()

async def clear_cache() -> None:
    await asyncio.to_thread(_clear_cache_sync)
