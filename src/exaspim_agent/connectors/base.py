from __future__ import annotations

from abc import ABC, abstractmethod

from exaspim_agent.domain.models import SourceRecord


class DataConnector(ABC):
    name: str

    @abstractmethod
    def fetch(self) -> list[SourceRecord]:
        """Retrieve read-only records from a source system."""

    @abstractmethod
    def describe(self) -> dict[str, str]:
        """Describe the connector and its access pattern."""
