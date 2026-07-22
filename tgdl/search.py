from abc import ABC, abstractmethod
from typing import List, Optional
from tgdl.models import MessageMetadata
import tgdl.database as db

class SearchEngineInterface(ABC):
    """Abstract interface for searching cached Telegram messages."""

    @abstractmethod
    async def search(
        self,
        query: Optional[str] = None,
        sort_by: str = "message_id",
        sort_desc: bool = True,
        limit: int = 300,
        offset: int = 0
    ) -> List[MessageMetadata]:
        pass

class SearchEngine(SearchEngineInterface):
    """Default SQLite-backed search engine with wildcard pattern support."""

    async def search(
        self,
        query: Optional[str] = None,
        sort_by: str = "message_id",
        sort_desc: bool = True,
        limit: int = 300,
        offset: int = 0
    ) -> List[MessageMetadata]:
        """Execute a case-insensitive search query over SQLite."""
        return await db.get_cached_messages(
            search_query=query,
            sort_by=sort_by,
            sort_desc=sort_desc,
            limit=limit,
            offset=offset
        )
