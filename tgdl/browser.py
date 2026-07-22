from typing import List, Optional
from tgdl.telegram_client import TelegramClientWrapper
import tgdl.database as db
from tgdl.models import MessageMetadata

class Browser:
    def __init__(self, client_wrapper: TelegramClientWrapper) -> None:
        self.client_wrapper = client_wrapper

    async def sync_messages(self) -> int:
        """Fetch and cache new messages from Saved Messages incrementally."""
        max_id = await db.get_max_message_id()
        new_messages = await self.client_wrapper.fetch_media_messages(min_id=max_id)
        if new_messages:
            await db.cache_messages(new_messages)
        return len(new_messages)

    async def load_messages(
        self,
        search_query: Optional[str] = None,
        sort_by: str = "message_id",
        sort_desc: bool = True,
        category_filter: Optional[str] = None,
        limit: int = 300,
        offset: int = 0
    ) -> List[MessageMetadata]:
        """Load paged messages from SQLite using WAL-indexed fast queries."""
        return await db.get_cached_messages(
            search_query=search_query,
            sort_by=sort_by,
            sort_desc=sort_desc,
            category_filter=category_filter,
            limit=limit,
            offset=offset
        )
