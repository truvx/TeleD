from typing import List, Optional
from tgdl.models import MessageMetadata
import tgdl.database as db

class MessageRepository:
    """Repository interface handling MessageMetadata persistence operations."""

    async def get_by_id(self, message_id: int) -> Optional[MessageMetadata]:
        return await db.get_message(message_id)

    async def get_all(
        self,
        search_query: Optional[str] = None,
        sort_by: str = "message_id",
        sort_desc: bool = True,
        limit: int = 300,
        offset: int = 0
    ) -> List[MessageMetadata]:
        return await db.get_cached_messages(
            search_query=search_query,
            sort_by=sort_by,
            sort_desc=sort_desc,
            limit=limit,
            offset=offset
        )

    async def save_batch(self, messages: List[MessageMetadata]) -> None:
        await db.cache_messages(messages)

    async def update_status(self, message_id: int, status: str, downloaded_bytes: int, path: Optional[str] = None) -> None:
        await db.update_download_status(message_id, status, downloaded_bytes, path)

    async def delete_by_id(self, message_id: int) -> None:
        await db.delete_cached_message(message_id)
