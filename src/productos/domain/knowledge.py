from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class DocumentFormat(StrEnum):
    MARKDOWN = "markdown"
    TEXT = "text"


class KnowledgeStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class Sensitivity(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class EvidenceAvailability(StrEnum):
    EVIDENCE_FOUND = "evidence_found"
    NO_EVIDENCE_FOUND = "no_evidence_found"
    EVIDENCE_INACCESSIBLE = "evidence_inaccessible"
    EVIDENCE_AMBIGUOUS = "evidence_ambiguous"


class KnowledgeIngestRequest(BaseModel):
    user_id: UUID | None = None
    tenant_id: UUID | None = None
    source_type: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=1_000)
    content: str = Field(min_length=1, max_length=2_000_000)
    document_format: DocumentFormat = DocumentFormat.MARKDOWN
    summary: str | None = Field(default=None, max_length=10_000)
    author: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, max_length=500)
    workspace: str | None = Field(default=None, max_length=500)
    project: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=2_000)
    source_created_at: datetime | None = None
    source_updated_at: datetime | None = None
    authority_score: float = Field(default=0.7, ge=0, le=1)
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    access_boundary: str = Field(default="user", max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeItem(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    user_id: UUID
    source_type: str
    source_id: str
    title: str
    content: str
    content_checksum: str
    document_format: DocumentFormat
    summary: str | None = None
    author: str | None = None
    owner: str | None = None
    workspace: str | None = None
    project: str | None = None
    url: str | None = None
    source_created_at: datetime | None = None
    source_updated_at: datetime | None = None
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    authority_score: float = Field(ge=0, le=1)
    sensitivity: Sensitivity
    access_boundary: str
    status: KnowledgeStatus = KnowledgeStatus.ACTIVE
    supersedes_id: UUID | None = None
    embedding_provider: str
    embedding_dimension: int = Field(gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedSection(BaseModel):
    title: str | None = None
    parent_title: str | None = None
    content: str


class KnowledgeChunk(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    knowledge_item_id: UUID
    tenant_id: UUID
    user_id: UUID
    chunk_index: int = Field(ge=0)
    content: str
    token_count: int = Field(gt=0)
    embedding: list[float]
    section_title: str | None = None
    parent_section: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeIngestResult(BaseModel):
    item: KnowledgeItem
    chunk_count: int
    outcome: Literal["created", "unchanged", "superseded"]


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=20_000)
    user_id: UUID | None = None
    tenant_id: UUID | None = None
    source_types: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    updated_after: datetime | None = None
    limit: int = Field(default=8, ge=1, le=50)


class QueryAnalysis(BaseModel):
    original_query: str
    search_queries: list[str]
    keywords: list[str]
    entities: list[str] = Field(default_factory=list)
    time_constraints: dict[str, str] = Field(default_factory=dict)
    source_preferences: list[str] = Field(default_factory=list)
    requires_freshness: bool = False


class RetrievalCandidate(BaseModel):
    chunk: KnowledgeChunk
    item: KnowledgeItem
    semantic_score: float = Field(default=0, ge=0, le=1)
    lexical_score: float = Field(default=0, ge=0, le=1)
    combined_score: float = Field(default=0, ge=0)


class Citation(BaseModel):
    citation_id: str
    source_type: str
    source_id: str
    title: str
    url: str | None = None
    knowledge_item_id: UUID | None = None
    chunk_id: UUID | None = None
    excerpt: str
    source_updated_at: datetime | None = None


class EvidenceItem(BaseModel):
    id: str
    topic: str
    content: str
    source_type: str
    source_id: str
    title: str
    url: str | None = None
    knowledge_item_id: UUID | None = None
    chunk_id: UUID | None = None
    authority: float = Field(ge=0, le=1)
    relevance: float = Field(ge=0, le=1)
    freshness: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_updated_at: datetime | None = None
    section_title: str | None = None


class EvidenceContradiction(BaseModel):
    evidence_ids: tuple[str, str]
    description: str
    confidence: float = Field(ge=0, le=1)
    likely_current_evidence_id: str | None = None
    inference_rationale: str | None = None


class EvidencePacket(BaseModel):
    question: str
    availability: EvidenceAvailability
    evidence: list[EvidenceItem] = Field(default_factory=list)
    contradictions: list[EvidenceContradiction] = Field(default_factory=list)
    known_unknowns: list[str] = Field(default_factory=list)
    source_coverage: dict[str, int] = Field(default_factory=dict)
    citations: list[Citation] = Field(default_factory=list)


class KnowledgeItemDetail(BaseModel):
    item: KnowledgeItem
    chunks: list[KnowledgeChunk]
