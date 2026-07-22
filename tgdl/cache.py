from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import tgdl.database as db
from tgdl.models import MessageMetadata

class BaseCacheProvider(ABC):
    """Abstract base class for cache providers."""

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        pass

    @abstractmethod
    async def set(self, key: str, value: Any) -> None:
        pass

    @abstractmethod
    async def clear(self) -> None:
        pass

class MemoryCache(BaseCacheProvider):
    """Fast in-memory cache implementation."""

    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}

    async def get(self, key: str) -> Optional[Any]:
        return self._store.get(key)

    async def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    async def clear(self) -> None:
        self._store.clear()

class SQLiteMessageCache(BaseCacheProvider):
    """SQLite-backed message metadata cache implementation."""

    async def get(self, key: str) -> Optional[MessageMetadata]:
        if key.isdigit():
            return await db.get_message(int(key))
        return None

    async def set(self, key: str, value: Any) -> None:
        if isinstance(value, MessageMetadata):
            await db.cache_messages([value])

    async def clear(self) -> None:
        await db.clear_cache()
