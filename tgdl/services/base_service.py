from abc import ABC, abstractmethod

class BaseService(ABC):
    """Abstract base class for all application services."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize service resources."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Release service resources."""
        pass
