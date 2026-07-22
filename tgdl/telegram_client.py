import os
import asyncio
from typing import List, Optional
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, ApiIdInvalidError
from telethon.tl.types import MessageMediaWebPage, DocumentAttributeVideo, DocumentAttributeAudio

from tgdl.config import API_ID, API_HASH, SESSION_PATH
from tgdl.models import MessageMetadata

class TelegramClientWrapper:
    """Wrapper managing Telethon client connection, session reuse, and message metadata scanning."""

    def __init__(self, session_path: str = SESSION_PATH) -> None:
        self.session_path = session_path
        self.client: Optional[TelegramClient] = None

    async def connect(self) -> bool:
        session_dir = os.path.dirname(self.session_path)
        if session_dir:
            os.makedirs(session_dir, exist_ok=True)

        if not API_ID or not API_HASH:
            raise ValueError("API_ID or API_HASH missing in configuration.")

        self.client = TelegramClient(self.session_path, API_ID, API_HASH)
        await self.client.connect()

        return await self.client.is_user_authorized()

    async def disconnect(self) -> None:
        if self.client:
            await self.client.disconnect()
            self.client = None

    async def fetch_media_messages(self, min_id: int = 0) -> List[MessageMetadata]:
        if not self.client or not await self.client.is_user_authorized():
            raise RuntimeError("Telegram client is not connected or authorized.")

        messages: List[MessageMetadata] = []
        async for msg in self.client.iter_messages("me", min_id=min_id):
            if not msg.media or isinstance(msg.media, MessageMediaWebPage):
                continue

            file_helper = msg.file
            if not file_helper:
                continue

            ext = (file_helper.ext or "").lower()
            filename = file_helper.name
            if not filename:
                if msg.photo:
                    filename = f"photo_{msg.id}{ext or '.jpg'}"
                    ext = ext or ".jpg"
                else:
                    filename = f"media_{msg.id}{ext or '.bin'}"
                    ext = ext or ".bin"

            if not ext and "." in filename:
                ext = "." + filename.rsplit(".", 1)[-1].lower()

            duration: Optional[int] = None
            resolution: Optional[str] = None

            if msg.document and msg.document.attributes:
                for attr in msg.document.attributes:
                    if hasattr(attr, "duration") and attr.duration:
                        duration = int(attr.duration)
                    if hasattr(attr, "w") and hasattr(attr, "h") and attr.w and attr.h:
                        resolution = f"{attr.w}x{attr.h}"
            elif msg.photo and hasattr(msg.photo, "sizes") and msg.photo.sizes:
                largest = msg.photo.sizes[-1]
                if hasattr(largest, "w") and hasattr(largest, "h") and largest.w and largest.h:
                    resolution = f"{largest.w}x{largest.h}"

            upload_date = msg.date.isoformat() if msg.date else ""
            messages.append(
                MessageMetadata(
                    message_id=msg.id,
                    filename=filename,
                    extension=ext,
                    file_size=file_helper.size or 0,
                    mime_type=file_helper.mime_type or "application/octet-stream",
                    upload_date=upload_date,
                    download_status="pending",
                    downloaded_bytes=0,
                    chat_id=msg.chat_id or 0,
                    path=None,
                    file_hash=f"tg_{msg.id}",
                    duration=duration,
                    resolution=resolution
                )
            )

        return messages
