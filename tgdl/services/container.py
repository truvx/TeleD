from typing import Any, Dict, Type, TypeVar
from tgdl.services.base_service import BaseService

T = TypeVar("T")

class ServiceContainer:
    """Dependency Injection service registry and lifecycle manager."""

    def __init__(self) -> None:
        self._services: Dict[Type[Any], Any] = {}

    def register(self, service_type: Type[T], instance: T) -> None:
        """Register a service singleton instance."""
        self._services[service_type] = instance

    def get(self, service_type: Type[T]) -> T:
        """Retrieve a registered service instance."""
        if service_type not in self._services:
            raise KeyError(f"Service '{service_type.__name__}' is not registered in container.")
        return self._services[service_type]

    async def initialize_all(self) -> None:
        """Initialize all registered services inheriting from BaseService."""
        for service in self._services.values():
            if isinstance(service, BaseService):
                await service.initialize()

    async def shutdown_all(self) -> None:
        """Shutdown all registered services inheriting from BaseService."""
        for service in self._services.values():
            if isinstance(service, BaseService):
                await service.shutdown()

# Global DI container singleton
container = ServiceContainer()
