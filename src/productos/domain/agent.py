from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Intent(StrEnum):
    CHAT = "chat"


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=50_000)
    session_id: UUID | None = None
    conversation_id: UUID | None = None
    working_session_id: UUID | None = None
    user_id: UUID | None = None
    tenant_id: UUID | None = None
    workspace_id: str | None = Field(default=None, max_length=500)


class AgentState(BaseModel):
    run_id: UUID = Field(default_factory=uuid4)
    session_id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID | None = None
    working_session_id: UUID | None = None
    user_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID = Field(default_factory=uuid4)
    request: str
    intent: Intent = Intent.CHAT
    mode: str = "default"
    status: RunStatus = RunStatus.CREATED
    plan: dict[str, Any] | None = None
    retrieved_context: list[dict[str, Any]] = Field(default_factory=list)
    memories: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    response: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_request(
        cls,
        request: ChatRequest,
        default_user_id: UUID | None = None,
        default_tenant_id: UUID | None = None,
    ) -> "AgentState":
        values: dict[str, Any] = {
            "request": request.message,
            "conversation_id": request.conversation_id,
            "working_session_id": request.working_session_id,
        }
        if request.session_id is not None:
            values["session_id"] = request.session_id
        if request.user_id is not None:
            values["user_id"] = request.user_id
        elif default_user_id is not None:
            values["user_id"] = default_user_id
        if request.tenant_id is not None:
            values["tenant_id"] = request.tenant_id
        elif default_tenant_id is not None:
            values["tenant_id"] = default_tenant_id
        return cls(**values)
