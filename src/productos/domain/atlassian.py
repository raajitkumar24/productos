from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RetrievalStrategy(StrEnum):
    MEMORY_ONLY = "memory_only"
    INDEX_ONLY = "index_only"
    LIVE_ONLY = "live_only"
    INDEX_PLUS_LIVE = "index_plus_live"


class AtlassianSite(BaseModel):
    cloud_id: str
    site_url: str
    site_name: str
    user_identity: str | None = None
    accessible_projects: list[str] = Field(default_factory=list)
    accessible_spaces: list[str] = Field(default_factory=list)


class SourceReference(BaseModel):
    provider: str = "atlassian"
    source_type: str
    source_id: str
    title: str
    url: str | None = None
    cloud_id: str
    retrieved_at: datetime
    updated_at: datetime | None = None
    authority: float = Field(default=0.8, ge=0, le=1)
    access_boundary: str


class JiraSearchIntent(BaseModel):
    projects: list[str] = Field(default_factory=list, max_length=20)
    text: list[str] = Field(default_factory=list, max_length=20)
    statuses: list[str] = Field(default_factory=list, max_length=20)
    issue_types: list[str] = Field(default_factory=list, max_length=20)
    owners: list[str] = Field(default_factory=list, max_length=20)
    updated_after: datetime | None = None
    limit: int = Field(default=50, ge=1, le=100)

    @field_validator("projects")
    @classmethod
    def validate_projects(cls, values: list[str]) -> list[str]:
        if any(not value.replace("-", "").isalnum() for value in values):
            raise ValueError("Project keys may contain only letters, numbers, and hyphens")
        return values


class ConfluenceSearchIntent(BaseModel):
    spaces: list[str] = Field(default_factory=list, max_length=20)
    text: list[str] = Field(default_factory=list, max_length=20)
    labels: list[str] = Field(default_factory=list, max_length=20)
    contributors: list[str] = Field(default_factory=list, max_length=20)
    updated_after: datetime | None = None
    limit: int = Field(default=50, ge=1, le=100)

    @field_validator("spaces")
    @classmethod
    def validate_spaces(cls, values: list[str]) -> list[str]:
        if any(not value.replace("-", "").replace("_", "").isalnum() for value in values):
            raise ValueError("Space keys contain unsupported characters")
        return values


class JiraIssue(BaseModel):
    key: str
    title: str
    description: str | None = None
    issue_type: str | None = None
    status: str | None = None
    priority: str | None = None
    assignee: str | None = None
    reporter: str | None = None
    project: str
    parent: str | None = None
    epic: str | None = None
    labels: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    resolution: str | None = None
    links: list[str] = Field(default_factory=list)
    source: SourceReference
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConfluencePage(BaseModel):
    page_id: str
    title: str
    content: str
    space: str
    author: str | None = None
    owner: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    parent_page_id: str | None = None
    labels: list[str] = Field(default_factory=list)
    version: int | None = None
    source: SourceReference
    metadata: dict[str, Any] = Field(default_factory=dict)


class AtlassianRecord(BaseModel):
    record_type: str
    record_id: str
    title: str
    content: str | None = None
    source: SourceReference
    metadata: dict[str, Any] = Field(default_factory=dict)


class CurrentState(BaseModel):
    topic: str
    definition: str | None = None
    product_status: str | None = None
    implementation_status: str | None = None
    owners: list[str] = Field(default_factory=list)
    open_work: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    recent_changes: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)
    strategy: RetrievalStrategy


class CoverageStatus(StrEnum):
    IMPLEMENTED = "implemented"
    IN_PROGRESS = "in_progress"
    PLANNED = "planned"
    NO_EVIDENCE = "no_evidence"
    OUT_OF_SCOPE = "out_of_scope"
    AMBIGUOUS = "ambiguous"


class RequirementCoverage(BaseModel):
    requirement: str
    status: CoverageStatus
    issue_keys: list[str] = Field(default_factory=list)
    evidence: list[SourceReference] = Field(default_factory=list)
    explanation: str


class SpecExecutionComparison(BaseModel):
    spec_page_id: str
    spec_title: str
    requirements: list[RequirementCoverage]
    unknowns: list[str] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)


class CurrentStateRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=10_000)
    user_id: UUID | None = None
    tenant_id: UUID | None = None
    cloud_id: str | None = Field(default=None, max_length=500)


class SpecExecutionRequest(BaseModel):
    page_id: str = Field(min_length=1, max_length=500)
    projects: list[str] = Field(default_factory=list, max_length=20)
    user_id: UUID | None = None
    tenant_id: UUID | None = None
    cloud_id: str | None = Field(default=None, max_length=500)
