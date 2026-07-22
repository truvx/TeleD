from abc import ABC, abstractmethod
from typing import List, Optional
from rapidfuzz import fuzz

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
    """RapidFuzz-powered instant search engine supporting wildcards (*.mkv, *.pdf, *.zip, *.iso) and fuzzy scoring."""

    async def search(
        self,
        query: Optional[str] = None,
        sort_by: str = "message_id",
        sort_desc: bool = True,
        limit: int = 300,
        offset: int = 0
    ) -> List[MessageMetadata]:
        """Execute fast case-insensitive query with RapidFuzz scoring over 100k indexed SQLite records."""
        candidates = await db.get_cached_messages(
            search_query=query,
            sort_by=sort_by,
            sort_desc=sort_desc,
            limit=limit,
            offset=offset
        )

        if not query or not query.strip():
            return candidates

        q = query.strip()
        # Wildcard extensions match directly from indexed query
        if "*" in q or "?" in q:
            return candidates

        # RapidFuzz scoring for partial text queries
        scored = []
        for msg in candidates:
            score = max(
                fuzz.partial_ratio(q.lower(), msg.filename.lower()),
                fuzz.partial_ratio(q.lower(), msg.extension.lower()),
                fuzz.partial_ratio(q.lower(), msg.mime_type.lower())
            )
            scored.append((score, msg))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [msg for _, msg in scored]
