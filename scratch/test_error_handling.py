import asyncio
import os
import sqlite3
import pytest
from tgdl.database import init_db, get_cached_messages, DATABASE_PATH, _recover_corrupted_db
from tgdl.models import MessageMetadata
from tgdl.downloader import Downloader
from tgdl.telegram_client import TelegramClientWrapper

async def test_corrupted_db_recovery():
    db_dir = os.path.dirname(DATABASE_PATH)
    os.makedirs(db_dir, exist_ok=True)
    with open(DATABASE_PATH, "wb") as f:
        f.write(b"CORRUPTED MALFORMED DATA HEADER HERE NOT SQLITE")
    
    await init_db()
    messages = await get_cached_messages()
    assert isinstance(messages, list)
    print("✓ Corrupted database auto-recovery verified!")

async def main():
    await test_corrupted_db_recovery()

if __name__ == "__main__":
    asyncio.run(main())
