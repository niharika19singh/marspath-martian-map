from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.app.data_sources.schemas.models import (
    ConnectionState,
    DataProduct,
    DataSourceEntry,
)


class BaseDataSourceConnector(ABC):
    """Abstract base class for official NASA data source connectors."""

    def __init__(self, entry: DataSourceEntry) -> None:
        self.entry = entry

    @abstractmethod
    async def check_connection(self) -> tuple[ConnectionState, str | None]:
        """Verify live network connection and access to official service."""
        pass

    @abstractmethod
    async def fetch_metadata(self) -> dict[str, Any]:
        """Retrieve authoritative metadata, capabilities, or service descriptor."""
        pass

    @abstractmethod
    async def list_products(self, limit: int = 50) -> list[DataProduct]:
        """Enumerate indexed or cached data products for the source."""
        pass
