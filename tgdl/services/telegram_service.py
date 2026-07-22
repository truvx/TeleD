import asyncio
import os
from typing import Dict, List, Optional, Any
from telethon import TelegramClient
from telethon.errors import (
    ApiIdInvalidError,
    FloodWaitError,
    AuthKeyUnregisteredError,
    SessionRevokedError,
    UserDeactivatedError
)
from telethon.tl.types import MessageMediaWebPage

from tgdl.services.base_service import BaseService
from tgdl.config import API_ID, API_HASH
from tgdl.constants import DEFAULT_SESSION_DIR
from tgdl.models import MessageMetadata

class TelegramService(BaseService):
    """Service handling Telethon connection, multi-account sessions, and Telegram API interaction."""

    def __init__(self, session_name: str = "session") -> None:
        self.session_name = session_name
        self.session_path = str(DEFAULT_SESSION_DIR / session_name)
        self.client: Optional[TelegramClient] = None
        self._user_info: Optional[Dict[str, Any]] = None

    async def initialize(self) -> None:
        await self.connect()

    async def shutdown(self) -> None:
        await self.disconnect()

    async def connect(self, session_name: Optional[str] = None) -> bool:
        if session_name:
            self.session_name = session_name
            self.session_path = str(DEFAULT_SESSION_DIR / session_name)

        os.makedirs(DEFAULT_SESSION_DIR, exist_ok=True)
        if not API_ID or not API_HASH:
            raise ValueError("Invalid API Credentials: TELEGRAM_API_ID and TELEGRAM_API_HASH must be configured.")

        try:
            self.client = TelegramClient(self.session_path, API_ID, API_HASH, auto_reconnect=True)
            await self.client.connect()
            is_auth = await self.client.is_user_authorized()
            if is_auth:
                await self.get_me()
            return is_auth
        except ApiIdInvalidError:
            raise ValueError("Invalid Telegram API credentials. Please check API_ID and API_HASH.")
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 1)
            return await self.connect()

    async def disconnect(self) -> None:
        if self.client:
            await self.client.disconnect()
            self.client = None

    async def is_logged_in(self) -> bool:
        if not self.client or not self.client.is_connected():
            return False
        try:
            return await self.client.is_user_authorized()
        except (AuthKeyUnregisteredError, SessionRevokedError, UserDeactivatedError):
            return False

    async def get_me(self) -> Dict[str, Any]:
        if not self.client or not await self.is_logged_in():
            return {"username": "Guest", "first_name": "Not Connected", "id": 0}

        me = await self.client.get_me()
        self._user_info = {
            "id": me.id,
            "username": me.username or f"User_{me.id}",
            "first_name": me.first_name or "",
            "phone": me.phone or ""
        }
        return self._user_info

    async def get_saved_messages(self, min_id: int = 0) -> List[MessageMetadata]:
        if not self.client or not await self.is_logged_in():
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
