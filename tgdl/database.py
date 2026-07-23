import sqlite3
import os
import shutil
import asyncio
import time
from datetime import datetime
from typing import List, Optional, Tuple
from tgdl.config import DATABASE_PATH
from tgdl.models import MessageMetadata

def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA cache_size=-64000;")
    return conn

def _handle_db_error(e: Exception) -> None:
    err_str = str(e).lower()
    if isinstance(e, sqlite3.DatabaseError) and ("malformed" in err_str or "corrupt" in err_str):
        _recover_corrupted_db()

def _recover_corrupted_db() -> None:
    if os.path.exists(DATABASE_PATH):
        bak_path = f"{DATABASE_PATH}.corrupted.{int(datetime.now().timestamp())}"
        try: shutil.move(DATABASE_PATH, bak_path)
        except OSError: pass
    _init_db_sync()

def _init_db_sync() -> None:
    db_dir = os.path.dirname(DATABASE_PATH)
    if db_dir: os.makedirs(db_dir, exist_ok=True)
    try:
        with _get_db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    message_id INTEGER PRIMARY KEY, filename TEXT NOT NULL, extension TEXT NOT NULL DEFAULT '',
                    mime_type TEXT NOT NULL, size INTEGER NOT NULL, date TEXT NOT NULL,
                    chat_id INTEGER NOT NULL DEFAULT 0, downloaded INTEGER NOT NULL DEFAULT 0,
                    local_path TEXT, hash TEXT, duration INTEGER, resolution TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, message_id INTEGER NOT NULL, filename TEXT NOT NULL,
                    size INTEGER NOT NULL, downloaded_bytes INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL,
                    completed_at TEXT, local_path TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)
            """)
            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_files_filename ON files(filename);",
                "CREATE INDEX IF NOT EXISTS idx_files_date ON files(date);",
                "CREATE INDEX IF NOT EXISTS idx_files_size ON files(size);",
                "CREATE INDEX IF NOT EXISTS idx_files_downloaded ON files(downloaded);",
                "CREATE INDEX IF NOT EXISTS idx_files_message_id ON files(message_id);",
                "CREATE INDEX IF NOT EXISTS idx_files_ext ON files(extension);",
                "CREATE INDEX IF NOT EXISTS idx_files_ext_date ON files(extension, date);",
                "CREATE INDEX IF NOT EXISTS idx_files_dl_date ON files(downloaded, date);",
                "CREATE INDEX IF NOT EXISTS idx_files_fn_date ON files(filename, date);"
            ]: conn.execute(idx_sql)
            conn.commit()
    except Exception as e: _handle_db_error(e)

async def init_db() -> None: await asyncio.to_thread(_init_db_sync)

def _set_setting_sync(key: str, value: str) -> None:
    try:
        with _get_db() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
            conn.commit()
    except Exception as e: _handle_db_error(e)

async def set_setting(key: str, value: str) -> None: await asyncio.to_thread(_set_setting_sync, key, value)

def _get_setting_sync(key: str, default: str = "") -> str:
    try:
        with _get_db() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row[0] if row else default
    except Exception as e:
        _handle_db_error(e)
        return default

async def get_setting(key: str, default: str = "") -> str: return await asyncio.to_thread(_get_setting_sync, key, default)

def _cache_messages_sync(messages: List[MessageMetadata]) -> None:
    try:
        with _get_db() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO files 
                (message_id, filename, extension, mime_type, size, date, chat_id, downloaded, local_path, hash, duration, resolution)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    m.message_id, m.filename, m.extension, m.mime_type, m.file_size, m.upload_date,
                    m.chat_id, 1 if m.download_status == "completed" else 0, m.path, m.file_hash, m.duration, m.resolution
                )
                for m in messages
            ])
            conn.commit()
    except Exception as e: _handle_db_error(e)

async def cache_messages(messages: List[MessageMetadata]) -> None:
    if messages: await asyncio.to_thread(_cache_messages_sync, messages)

def _build_where_clause(search_query: Optional[str], category_filter: Optional[str]) -> Tuple[str, list]:
    where_parts, params = [], []
    if search_query:
        q = search_query.strip()
        pattern = q.replace("*", "%").replace("?", "_") if ("*" in q or "?" in q) else f"%{q}%"
        where_parts.append("(filename LIKE ? OR extension LIKE ? OR date LIKE ? OR mime_type LIKE ?)")
        params.extend([pattern, pattern, pattern, pattern])
        
    if category_filter:
        c = category_filter.lower()
        cat_map = {
            "videos": ("(extension IN ('.mp4','.mkv','.avi','.mov','.webm','.flv') OR mime_type LIKE 'video/%')"),
            "images": ("(extension IN ('.jpg','.jpeg','.png','.gif','.webp','.svg') OR mime_type LIKE 'image/%')"),
            "pdf": ("(extension = '.pdf' OR mime_type LIKE '%pdf%')"),
            "documents": ("(extension IN ('.pdf','.doc','.docx','.txt','.epub','.pages','.odt') OR mime_type LIKE 'text/%')"),
            "archives": ("(extension IN ('.zip','.rar','.7z','.tar','.gz','.bz2','.iso') OR mime_type LIKE '%zip%' OR mime_type LIKE '%compressed%')"),
            "audio": ("(extension IN ('.mp3','.flac','.wav','.ogg','.m4a','.aac') OR mime_type LIKE 'audio/%')")
        }
        if c in cat_map: where_parts.append(cat_map[c])
            
    where_str = " WHERE " + " AND ".join(where_parts) if where_parts else ""
    return where_str, params

def _get_cached_messages_sync(search_query: Optional[str] = None, sort_by: str = "message_id", sort_desc: bool = True, category_filter: Optional[str] = None, limit: int = 250, offset: int = 0) -> List[MessageMetadata]:
    valid_cols = {"filename": "filename", "size": "size", "date": "date", "extension": "extension", "downloaded": "downloaded", "message_id": "message_id"}
    col_name = valid_cols.get(sort_by.lower(), "message_id")
    direction = "DESC" if sort_desc else "ASC"
    
    where_str, params = _build_where_clause(search_query, category_filter)
    query = f"SELECT message_id, filename, extension, mime_type, size, date, chat_id, downloaded, local_path, hash, duration, resolution FROM files{where_str} ORDER BY {col_name} {direction} LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    try:
        with _get_db() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            
        return [
            MessageMetadata(
                message_id=row["message_id"], filename=row["filename"], extension=row["extension"],
                file_size=row["size"], mime_type=row["mime_type"], upload_date=row["date"],
                download_status="completed" if row["downloaded"] == 1 else "pending",
                downloaded_bytes=row["size"] if row["downloaded"] == 1 else 0,
                chat_id=row["chat_id"], path=row["local_path"], file_hash=row["hash"],
                duration=row["duration"], resolution=row["resolution"]
            )
            for row in rows
        ]
    except Exception as e:
        _handle_db_error(e)
        return []

async def get_cached_messages(search_query: Optional[str] = None, sort_by: str = "message_id", sort_desc: bool = True, category_filter: Optional[str] = None, limit: int = 250, offset: int = 0) -> List[MessageMetadata]:
    return await asyncio.to_thread(_get_cached_messages_sync, search_query, sort_by, sort_desc, category_filter, limit, offset)

def _get_filtered_totals_sync(search_query: Optional[str] = None, category_filter: Optional[str] = None) -> Tuple[int, int]:
    where_str, params = _build_where_clause(search_query, category_filter)
    query = f"SELECT COUNT(*), COALESCE(SUM(size), 0) FROM files{where_str}"
    try:
        with _get_db() as conn:
            row = conn.execute(query, params).fetchone()
            return (row[0], row[1]) if row else (0, 0)
    except Exception as e:
        _handle_db_error(e)
        return (0, 0)

async def get_filtered_totals(search_query: Optional[str] = None, category_filter: Optional[str] = None) -> Tuple[int, int]:
    return await asyncio.to_thread(_get_filtered_totals_sync, search_query, category_filter)

def _update_download_status_sync(message_id: int, status: str, downloaded_bytes: int, path: Optional[str] = None) -> None:
    try:
        with _get_db() as conn:
            is_dl = 1 if status == "completed" else 0
            if path is not None:
                conn.execute("UPDATE files SET downloaded = ?, local_path = ? WHERE message_id = ?", (is_dl, path, message_id))
            else:
                conn.execute("UPDATE files SET downloaded = ? WHERE message_id = ?", (is_dl, message_id))
                
            now = datetime.now().isoformat()
            conn.execute("INSERT INTO downloads (message_id, filename, size, downloaded_bytes, status, completed_at, local_path) SELECT message_id, filename, size, ?, ?, ?, ? FROM files WHERE message_id = ?", (downloaded_bytes, status, now, path or "", message_id))
            conn.commit()
    except Exception as e: _handle_db_error(e)

async def update_download_status(message_id: int, status: str, downloaded_bytes: int, path: Optional[str] = None) -> None:
    await asyncio.to_thread(_update_download_status_sync, message_id, status, downloaded_bytes, path)

async def record_download_history(message_id: int, filename: str, file_size: int, local_path: str) -> None:
    await update_download_status(message_id, "completed", file_size, local_path)

def _delete_cached_message_sync(message_id: int) -> None:
    try:
        with _get_db() as conn:
            conn.execute("DELETE FROM files WHERE message_id = ?", (message_id,))
            conn.execute("DELETE FROM downloads WHERE message_id = ?", (message_id,))
            conn.commit()
    except Exception as e: _handle_db_error(e)

async def delete_cached_message(message_id: int) -> None:
    await asyncio.to_thread(_delete_cached_message_sync, message_id)

def _get_max_message_id_sync() -> int:
    try:
        with _get_db() as conn:
            row = conn.execute("SELECT MAX(message_id) FROM files").fetchone()
            return row[0] if row and row[0] is not None else 0
    except Exception as e:
        _handle_db_error(e)
        return 0

async def get_max_message_id() -> int:
    return await asyncio.to_thread(_get_max_message_id_sync)

def _get_message_sync(message_id: int) -> Optional[MessageMetadata]:
    try:
        with _get_db() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT message_id, filename, extension, mime_type, size, date, chat_id, downloaded, local_path, hash, duration, resolution FROM files WHERE message_id = ?", (message_id,)).fetchone()
            if not row: return None
            return MessageMetadata(
                message_id=row["message_id"], filename=row["filename"], extension=row["extension"],
                file_size=row["size"], mime_type=row["mime_type"], upload_date=row["date"],
                download_status="completed" if row["downloaded"] == 1 else "pending",
                downloaded_bytes=row["size"] if row["downloaded"] == 1 else 0,
                chat_id=row["chat_id"], path=row["local_path"], file_hash=row["hash"],
                duration=row["duration"], resolution=row["resolution"]
            )
    except Exception as e:
        _handle_db_error(e)
        return None

async def get_message(message_id: int) -> Optional[MessageMetadata]:
    return await asyncio.to_thread(_get_message_sync, message_id)

def _clear_cache_sync() -> None:
    try:
        with _get_db() as conn:
            conn.execute("DELETE FROM files")
            conn.execute("DELETE FROM downloads")
            conn.execute("DELETE FROM settings")
            conn.commit()
    except Exception as e: _handle_db_error(e)

async def clear_cache() -> None: await asyncio.to_thread(_clear_cache_sync)
