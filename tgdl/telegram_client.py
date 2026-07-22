import asyncio
import os
from typing import AsyncGenerator, List, Optional
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import MessageMediaWebPage
from tgdl.config import API_ID, API_HASH, SESSION_PATH
from tgdl.models import MessageMetadata

class TelegramClientWrapper:
    def __init__(self) -> None:
        self.client: Optional[TelegramClient] = None

    async def connect(self) -> bool:
        """Initialize and connect the client."""
        if not API_ID or not API_HASH:
            raise ValueError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be configured.")
        
        self.client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
        await self.client.connect()
        return await self.client.is_user_authorized()

    async def is_authorized(self) -> bool:
        """Check if current session is authorized."""
        if not self.client:
            return False
        return await self.client.is_user_authorized()

    async def authorize_interactive(self) -> None:
        """Execute a console interactive sign-in flow."""
        if not self.client:
            raise RuntimeError("Client not connected.")
        
        print("\n=== Telegram Downloader (TGDL) Authorization ===")
        phone = input("Enter your phone number (with country code, e.g. +1234567890): ").strip()
        sent_code = await self.client.send_code_request(phone)
        
        code = input("Enter the login code you received: ").strip()
        try:
            await self.client.sign_in(phone, code, password=None)
        except SessionPasswordNeededError:
            password = input("2-Step Verification enabled. Enter password: ").strip()
            await self.client.sign_in(password=password)
        
        print("Successfully authorized! Session saved.")

    async def fetch_media_messages(self, min_id: int = 0) -> List[MessageMetadata]:
        """Fetch media/document messages from Saved Messages since min_id."""
        if not self.client:
            raise RuntimeError("Client not connected.")
            
        messages: List[MessageMetadata] = []
        # 'me' refers to the user's own "Saved Messages" chat
        async for msg in self.client.iter_messages("me", min_id=min_id):
            # Ignore messages without media, or with webpage media (e.g. link previews)
            if not msg.media or isinstance(msg.media, MessageMediaWebPage):
                continue
            
            # Use Telethon file helper to extract metadata
            file_helper = msg.file
            if not file_helper:
                continue

            # Resolve filename. Generate a name if empty (e.g. photos/voice memos)
            filename = file_helper.name
            if not filename:
                ext = file_helper.ext or ""
                if msg.photo:
                    filename = f"photo_{msg.id}{ext or '.jpg'}"
                else:
                    filename = f"media_{msg.id}{ext or '.bin'}"

            # Format status, date
            upload_date = msg.date.isoformat() if msg.date else ""
            
            metadata = MessageMetadata(
                message_id=msg.id,
                filename=filename,
                file_size=file_helper.size or 0,
                mime_type=file_helper.mime_type or "application/octet-stream",
                upload_date=upload_date,
                download_status="pending",
                downloaded_bytes=0,
                path=None
            )
            messages.append(metadata)
            
        return messages

    async def disconnect(self) -> None:
        """Disconnect the Telegram client session."""
        if self.client:
            await self.client.disconnect()
