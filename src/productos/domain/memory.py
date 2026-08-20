from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class MemoryType(StrEnum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    PREFERENCE = "preference"
    DECISION = "decision"
    BELIEF = "belief"


class MemoryStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class ProvenanceType(StrEnum):
    EXPLICIT_USER = "explicit_user"
    TOOL_SOURCE = "tool_source"
    SYSTEM_SOURCE = "system_source"
    INFERRED = "inferred"


class MemoryRelationshipType(StrEnum):
    SUPERSEDES = "supersedes"
    CONTRADICTS = "contradicts"
    SUPPORTS = "supports"
    DUPLICATES = "duplicates"
    CORRECTS = "corrects"


class MemoryCreate(BaseModel):
    user_id: UUID | None = None
    memory_type: MemoryType
    content: str = Field(min_length=1, max_length=50_000)
    summary: str | None = Field(default=None, max_length=1_000)
    confidence: float = Field(default=1.0, ge=0, le=1)
    importance: float = Field(default=0.5, ge=0, le=1)
    source_type: str = Field(default="user", min_length=1, max_length=100)
    source_id: str | None = Field(default=None, max_length=500)
    provenance_type: ProvenanceType = ProvenanceType.EXPLICIT_USER
    memory_key: str | None = Field(default=None, max_length=240)
    expires_at: datetime | None = None


class MemoryCandidate(MemoryCreate):
    user_id: UUID


class Memory(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    memory_type: MemoryType
    content: str
    normalized_content: str
    summary: str | None = None
    confidence: float = Field(ge=0, le=1)
    importance: float = Field(ge=0, le=1)
    status: MemoryStatus
    source_type: str
    source_id: str | None = None
    provenance_type: ProvenanceType
    memory_key: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_accessed_at: datetime | None = None
    expires_at: datetime | None = None


class MemoryRelationship(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    from_memory_id: UUID
    to_memory_id: UUID
    relationship_type: MemoryRelationshipType
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MemoryWithRelationships(BaseModel):
    memory: Memory
    outgoing: list[MemoryRelationship] = Field(default_factory=list)
    incoming: list[MemoryRelationship] = Field(default_factory=list)


class MemoryPatch(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=50_000)
    summary: str | None = Field(default=None, max_length=1_000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    importance: float | None = Field(default=None, ge=0, le=1)
    status: MemoryStatus | None = None
    memory_key: str | None = Field(default=None, max_length=240)

    @model_validator(mode="after")
    def require_change(self) -> "MemoryPatch":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class MemoryWriteOutcome(StrEnum):
    CREATED = "created"
    DUPLICATE = "duplicate"
    SUPERSEDED = "superseded"
    RETAINED_AS_CANDIDATE = "retained_as_candidate"


class MemoryWriteResult(BaseModel):
    memory: Memory
    outcome: MemoryWriteOutcome
    related_memory_id: UUID | None = None


class BeliefStatus(StrEnum):
    ACTIVE = "active"
    WEAKENED = "weakened"
    CONTRADICTED = "contradicted"
    SUPERSEDED = "superseded"


class BeliefCreate(BaseModel):
    user_id: UUID | None = None
    statement: str = Field(min_length=1, max_length=50_000)
    confidence: float = Field(default=0.5, ge=0, le=1)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    belief_key: str | None = Field(default=None, max_length=240)


class Belief(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    memory_id: UUID
    statement: str
    confidence: float = Field(ge=0, le=1)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    status: BeliefStatus = BeliefStatus.ACTIVE


class DecisionStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    UNDER_REVIEW = "under_review"


class DecisionCreate(BaseModel):
    user_id: UUID | None = None
    title: str = Field(min_length=1, max_length=500)
    problem: str
    context: str
    decision: str
    rationale: str
    evidence: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    rejected_alternatives: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    owner: str | None = None
    status: DecisionStatus = DecisionStatus.PROPOSED
    review_at: datetime | None = None
    review_trigger: str | None = None
    validation_plan: str | None = None


class Decision(DecisionCreate):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    memory_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
