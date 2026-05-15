from __future__ import annotations

from pathlib import Path

from nexus_observability.config import StorageConfig
from nexus_observability.io import append_jsonl, read_jsonl
from nexus_observability.models import TraceSpan


class TraceRecorder:
    def __init__(self, storage: StorageConfig, base_dir: Path) -> None:
        self.storage = storage
        self.base_dir = base_dir

    def record(
        self,
        service: str,
        operation: str,
        duration_ms: float,
        trace_id: str,
        parent_span_id: str | None = None,
        attributes: dict | None = None,
    ) -> TraceSpan:
        span = TraceSpan(
            service=service,
            operation=operation,
            duration_ms=duration_ms,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            attributes=attributes or {},
        )
        append_jsonl(self.storage.traces_uri, self.base_dir, span)
        return span

    def read_all(self) -> list[dict]:
        return read_jsonl(self.storage.traces_uri, self.base_dir)

