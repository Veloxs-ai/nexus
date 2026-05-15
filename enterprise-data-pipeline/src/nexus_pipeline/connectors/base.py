from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable

from nexus_pipeline.config import SourceConfig


class Connector(ABC):
    def __init__(self, source: SourceConfig) -> None:
        self.source = source

    @abstractmethod
    def read(self, checkpoint: str | None = None) -> Iterable[dict[str, Any]]:
        """Read source records from the configured system."""

