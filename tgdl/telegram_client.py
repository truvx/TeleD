import os
import asyncio
import socket
from typing import List, Optional, Callable
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError, ApiIdInvalidError, AuthKeyUnregisteredError,
    SessionRevokedError, UserDeactivatedError, AuthKeyInvalidError, RPCError
)
from telethon.tl.types import MessageMediaWebPage, DocumentAttributeVideo, DocumentAttributeAudio

import tgdl.config as config
from tgdl.models import MessageMetadata

class TelegramClientWrapper:
    """Wrapper managing Telethon client connection, session reuse, proxy support, and network resiliency."""

    def __init__(self, session_path: Optional[str] = None) -> None:
        self.session_path = session_path or config.SESSION_PATH
        self.client: Optional[TelegramClient] = None

    async def connect(self) -> bool:
        session_path = self.session_path or config.SESSION_PATH
        session_dir = os.path.dirname(session_path)
        if session_dir:
            os.makedirs(session_dir, exist_ok=True)

        if not config.API_ID or not config.API_HASH:
            raise ValueError("API_ID or API_HASH missing in configuration.")

        proxy = config.get_proxy()
        try:
            if not self.client:
                kwargs = {"connection_retries": 5, "retry_delay": 1, "timeout": 10}
                if proxy: kwargs["proxy"] = proxy
                self.client = TelegramClient(session_path, config.API_ID, config.API_HASH, **kwargs)
            if not self.client.is_connected():
                await self.client.connect()
            return await self.client.is_user_authorized()
        except (AuthKeyUnregisteredError, SessionRevokedError, UserDeactivatedError, AuthKeyInvalidError) as e:
            raise RuntimeError(f"Session Expired: {e}") from e
        except (asyncio.TimeoutError, socket.error, ConnectionError, OSError) as e:
            raise ConnectionError(
                f"Network Connection Failed: Cannot reach Telegram servers.\n"
                f"Your network/ISP or firewall may be blocking direct Telegram IP connections.\n"
                f"If you are behind a firewall or restricted network, please enable a VPN or add SOCKS5/HTTP Proxy settings in .env (e.g. TELEGRAM_PROXY_HOST=127.0.0.1)."
            ) from e
        except ApiIdInvalidError as e:
            raise ValueError("Invalid Telegram API_ID or API_HASH credentials.") from e

    async def authorize_interactive(self) -> None:
        if not self.client: await self.connect()
        if self.client and not await self.client.is_user_authorized():
            await self.client.start()

    async def disconnect(self) -> None:
        if self.client:
            try: await self.client.disconnect()
            except Exception: pass
            self.client = None

    async def get_me(self) -> dict:
        if not self.client or not await self.client.is_user_authorized(): return {}
        me = await self.client.get_me()
        return {"id": me.id, "username": me.username, "first_name": me.first_name, "phone": me.phone} if me else {}

    async def fetch_media_messages(
        self,
        min_id: int = 0,
        progress_callback: Optional[Callable[[int, int, int], None]] = None
    ) -> List[MessageMetadata]:
        if not self.client: raise RuntimeError("Telegram client is not connected.")
        try:
            if not await self.client.is_user_authorized(): raise RuntimeError("Telegram session is not authorized.")
        except (AuthKeyUnregisteredError, SessionRevokedError, UserDeactivatedError):
            raise RuntimeError("Session Expired: Please re-authorize Telegram session.")

        messages: List[MessageMetadata] = []
        try:
            res = await self.client.get_messages("me", limit=1)
            total = res.total if res else 0
            scanned = 0
            async for msg in self.client.iter_messages("me", min_id=min_id):
                scanned += 1
                if msg.media and not isinstance(msg.media, MessageMediaWebPage):
                    file_helper = msg.file
                    if file_helper:
                        ext = (file_helper.ext or "").lower()
                        filename = file_helper.name
                        if not filename:
                            filename = f"photo_{msg.id}{ext or '.jpg'}" if msg.photo else f"media_{msg.id}{ext or '.bin'}"
                            ext = ext or (".jpg" if msg.photo else ".bin")
                        if not ext and "." in filename:
                            ext = "." + filename.rsplit(".", 1)[-1].lower()

                        duration, resolution = None, None
                        if msg.document and msg.document.attributes:
                            for attr in msg.document.attributes:
                                if hasattr(attr, "duration") and attr.duration: duration = int(attr.duration)
                                if hasattr(attr, "w") and hasattr(attr, "h") and attr.w and attr.h: resolution = f"{attr.w}x{attr.h}"
                        elif msg.photo and hasattr(msg.photo, "sizes") and msg.photo.sizes:
                            largest = msg.photo.sizes[-1]
                            if hasattr(largest, "w") and hasattr(largest, "h") and largest.w and largest.h: resolution = f"{largest.w}x{largest.h}"

                        messages.append(
                            MessageMetadata(
                                message_id=msg.id, filename=filename, extension=ext, file_size=file_helper.size or 0,
                                mime_type=file_helper.mime_type or "application/octet-stream", upload_date=msg.date.isoformat() if msg.date else "",
                                download_status="pending", downloaded_bytes=0, chat_id=msg.chat_id or 0,
                                path=None, file_hash=f"tg_{msg.id}", duration=duration, resolution=resolution
                            )
                        )
                if progress_callback and (scanned % 10 == 0 or scanned == total):
                    progress_callback(scanned, total, len(messages))
        except (asyncio.TimeoutError, socket.error, ConnectionError) as e:
            raise ConnectionError(f"Network Connection Interrupted: {e}") from e
        except RPCError as e:
            raise RuntimeError(f"Telegram Server RPC Error: {e}") from e

        return messages
