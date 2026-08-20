import asyncio
from collections import defaultdict
from uuid import UUID

from productos.domain.trace import TraceEvent


class InMemoryTraceRepository:
    def __init__(self) -> None:
        self._events: dict[UUID, list[TraceEvent]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def append(self, event: TraceEvent) -> None:
        async with self._lock:
            self._events[event.run_id].append(event)

    async def list_for_run(self, run_id: UUID) -> list[TraceEvent]:
        async with self._lock:
            return list(self._events.get(run_id, []))
