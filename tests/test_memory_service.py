from uuid import UUID

import pytest

from productos.domain.memory import (
    MemoryCandidate,
    MemoryStatus,
    MemoryType,
    MemoryWriteOutcome,
    ProvenanceType,
)
from productos.infrastructure.database import create_engine, create_session_factory
from productos.infrastructure.persistence import Base, SqlMemoryRepository
from productos.memory.service import MemoryService

USER_ID = UUID("00000000-0000-4000-8000-000000000001")


def candidate(
    content: str, provenance: ProvenanceType, memory_key: str = "response_tone"
) -> MemoryCandidate:
    return MemoryCandidate(
        user_id=USER_ID,
        memory_type=MemoryType.PREFERENCE,
        content=content,
        confidence=0.8,
        importance=0.7,
        source_type="test",
        provenance_type=provenance,
        memory_key=memory_key,
    )


@pytest.mark.asyncio
async def test_lower_authority_memory_cannot_displace_explicit_user_memory() -> None:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repository = SqlMemoryRepository(create_session_factory(engine))
    service = MemoryService(repository)

    explicit = await service.remember(candidate("formal responses", ProvenanceType.EXPLICIT_USER))
    inferred = await service.remember(candidate("casual responses", ProvenanceType.INFERRED))

    active = await repository.list(USER_ID, status=MemoryStatus.ACTIVE)
    pending = await repository.list(USER_ID, status=MemoryStatus.CANDIDATE)
    assert explicit.memory.id == active[0].id
    assert inferred.outcome == MemoryWriteOutcome.RETAINED_AS_CANDIDATE
    assert inferred.memory.id == pending[0].id
    await engine.dispose()


@pytest.mark.asyncio
async def test_returning_to_old_preference_creates_a_new_historical_event() -> None:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repository = SqlMemoryRepository(create_session_factory(engine))
    service = MemoryService(repository)

    first = await service.remember(
        candidate("concise responses", ProvenanceType.EXPLICIT_USER, "response_detail")
    )
    await service.remember(
        candidate("detailed responses", ProvenanceType.EXPLICIT_USER, "response_detail")
    )
    third = await service.remember(
        candidate("concise responses", ProvenanceType.EXPLICIT_USER, "response_detail")
    )

    all_memories = await repository.list(USER_ID)
    active = await repository.list(USER_ID, status=MemoryStatus.ACTIVE)
    assert len(all_memories) == 3
    assert third.memory.id != first.memory.id
    assert active[0].content == "concise responses"
    await engine.dispose()
