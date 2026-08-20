import re
from datetime import UTC, datetime
from uuid import UUID

from productos.application.repositories import MemoryRepository
from productos.domain.memory import (
    Memory,
    MemoryCandidate,
    MemoryPatch,
    MemoryRelationship,
    MemoryRelationshipType,
    MemoryStatus,
    MemoryWithRelationships,
    MemoryWriteOutcome,
    MemoryWriteResult,
    ProvenanceType,
)

_PROVENANCE_AUTHORITY = {
    ProvenanceType.INFERRED: 1,
    ProvenanceType.TOOL_SOURCE: 2,
    ProvenanceType.SYSTEM_SOURCE: 3,
    ProvenanceType.EXPLICIT_USER: 4,
}


def normalize_memory_content(content: str) -> str:
    return re.sub(r"\s+", " ", content.strip()).casefold()


class MemoryService:
    def __init__(self, repository: MemoryRepository) -> None:
        self._repository = repository

    async def remember(self, candidate: MemoryCandidate) -> MemoryWriteResult:
        normalized = normalize_memory_content(candidate.content)
        duplicate = await self._repository.find_duplicate(
            candidate.user_id, candidate.memory_type, normalized
        )
        if duplicate is not None:
            duplicate.last_accessed_at = datetime.now(UTC)
            duplicate.updated_at = datetime.now(UTC)
            await self._repository.update(duplicate)
            return MemoryWriteResult(
                memory=duplicate,
                outcome=MemoryWriteOutcome.DUPLICATE,
                related_memory_id=duplicate.id,
            )

        conflict: Memory | None = None
        if candidate.memory_key:
            conflict = await self._repository.find_active_by_key(
                candidate.user_id, candidate.memory_type, candidate.memory_key
            )

        status = MemoryStatus.ACTIVE
        outcome = MemoryWriteOutcome.CREATED
        relationship_type: MemoryRelationshipType | None = None
        if conflict is not None:
            incoming_authority = _PROVENANCE_AUTHORITY[candidate.provenance_type]
            existing_authority = _PROVENANCE_AUTHORITY[conflict.provenance_type]
            if incoming_authority >= existing_authority:
                outcome = MemoryWriteOutcome.SUPERSEDED
                relationship_type = MemoryRelationshipType.SUPERSEDES
            else:
                status = MemoryStatus.CANDIDATE
                outcome = MemoryWriteOutcome.RETAINED_AS_CANDIDATE
                relationship_type = MemoryRelationshipType.CONTRADICTS

        memory = Memory(
            user_id=candidate.user_id,
            memory_type=candidate.memory_type,
            content=candidate.content.strip(),
            normalized_content=normalized,
            summary=candidate.summary,
            confidence=candidate.confidence,
            importance=candidate.importance,
            status=status,
            source_type=candidate.source_type,
            source_id=candidate.source_id,
            provenance_type=candidate.provenance_type,
            memory_key=candidate.memory_key,
            expires_at=candidate.expires_at,
        )
        await self._repository.insert(memory)

        if conflict is not None and relationship_type is not None:
            await self._repository.add_relationship(
                MemoryRelationship(
                    from_memory_id=memory.id,
                    to_memory_id=conflict.id,
                    relationship_type=relationship_type,
                )
            )
            if relationship_type == MemoryRelationshipType.SUPERSEDES:
                conflict.status = MemoryStatus.SUPERSEDED
                conflict.updated_at = datetime.now(UTC)
                await self._repository.update(conflict)

        return MemoryWriteResult(
            memory=memory,
            outcome=outcome,
            related_memory_id=conflict.id if conflict else None,
        )

    async def inspect(self, memory_id: UUID, user_id: UUID) -> MemoryWithRelationships | None:
        memory = await self._repository.get(memory_id, user_id)
        if memory is None:
            return None
        outgoing, incoming = await self._repository.relationships(memory_id)
        return MemoryWithRelationships(memory=memory, outgoing=outgoing, incoming=incoming)

    async def patch(
        self, memory_id: UUID, user_id: UUID, patch: MemoryPatch
    ) -> MemoryWriteResult | None:
        existing = await self._repository.get(memory_id, user_id)
        if existing is None:
            return None

        if (
            patch.content is not None
            and normalize_memory_content(patch.content) != existing.normalized_content
        ):
            result = await self.remember(
                MemoryCandidate(
                    user_id=user_id,
                    memory_type=existing.memory_type,
                    content=patch.content,
                    summary=patch.summary
                    if "summary" in patch.model_fields_set
                    else existing.summary,
                    confidence=(
                        patch.confidence if patch.confidence is not None else existing.confidence
                    ),
                    importance=(
                        patch.importance if patch.importance is not None else existing.importance
                    ),
                    source_type="user_correction",
                    source_id=str(existing.id),
                    provenance_type=ProvenanceType.EXPLICIT_USER,
                    memory_key=(
                        patch.memory_key
                        if "memory_key" in patch.model_fields_set
                        else existing.memory_key
                    ),
                    expires_at=existing.expires_at,
                )
            )
            await self._repository.add_relationship(
                MemoryRelationship(
                    from_memory_id=result.memory.id,
                    to_memory_id=existing.id,
                    relationship_type=MemoryRelationshipType.CORRECTS,
                )
            )
            if existing.status == MemoryStatus.ACTIVE:
                existing.status = MemoryStatus.SUPERSEDED
                existing.updated_at = datetime.now(UTC)
                await self._repository.update(existing)
            return result

        if patch.summary is not None:
            existing.summary = patch.summary
        if patch.confidence is not None:
            existing.confidence = patch.confidence
        if patch.importance is not None:
            existing.importance = patch.importance
        if patch.status is not None:
            existing.status = patch.status
        if "memory_key" in patch.model_fields_set:
            existing.memory_key = patch.memory_key
        existing.updated_at = datetime.now(UTC)
        await self._repository.update(existing)
        return MemoryWriteResult(memory=existing, outcome=MemoryWriteOutcome.CREATED)
