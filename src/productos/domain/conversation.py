from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Conversation(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    title: str = Field(min_length=1, max_length=240)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Message(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    role: MessageRole
    content: str = Field(min_length=1, max_length=100_000)
    run_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConversationDetail(BaseModel):
    conversation: Conversation
    messages: list[Message] = Field(default_factory=list)


class WorkingSessionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class WorkingSessionCreate(BaseModel):
    user_id: UUID | None = None
    title: str = Field(min_length=1, max_length=240)
    objective: str = Field(min_length=1, max_length=10_000)
    workflow_type: str = Field(default="general", min_length=1, max_length=100)
    open_questions: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)


class WorkingSession(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    title: str
    objective: str
    workflow_type: str
    status: WorkingSessionStatus = WorkingSessionStatus.ACTIVE
    open_questions: list[str] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    artifact_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
