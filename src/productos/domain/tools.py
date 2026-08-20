from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ToolRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    DESTRUCTIVE = "destructive"


class ToolSensitivity(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class ToolErrorCode(StrEnum):
    TOOL_UNAVAILABLE = "tool_unavailable"
    AUTHENTICATION_FAILED = "authentication_failed"
    AUTHORIZATION_FAILED = "authorization_failed"
    INVALID_ARGUMENT = "invalid_argument"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    UPSTREAM_ERROR = "upstream_error"
    NO_RESULTS = "no_results"
    PARTIAL_RESULTS = "partial_results"
    BUDGET_EXCEEDED = "budget_exceeded"
    DUPLICATE_CALL = "duplicate_call"
    SITE_SELECTION_REQUIRED = "site_selection_required"


class ToolCallStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ToolDefinition(BaseModel):
    name: str
    description: str
    capability: str
    provider: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_level: ToolRisk
    read_only: bool
    requires_confirmation: bool
    idempotent: bool
    timeout_seconds: float = Field(gt=0, le=120)
    sensitivity: ToolSensitivity
    required_permissions: set[str] = Field(default_factory=set)
    version: str = "1.0.0"


class PermissionContext(BaseModel):
    tenant_id: UUID
    user_id: UUID
    workspace_id: str | None = None
    provider_identity: str | None = None
    permissions: set[str] = Field(default_factory=set)
    confirmed: bool = False


class ToolCallRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    tenant_id: UUID
    user_id: UUID
    workspace_id: str | None = None
    tool_name: str
    provider: str
    capability: str
    input_fingerprint: str
    status: ToolCallStatus
    error_code: ToolErrorCode | None = None
    result_count: int | None = None
    latency_ms: int | None = None
    contract_version: str
    adapter_version: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class ToolResult(BaseModel):
    call_id: UUID
    tool_name: str
    status: ToolCallStatus
    data: Any = None
    error_code: ToolErrorCode | None = None
    message: str | None = None
    result_count: int = 0
    partial: bool = False
    latency_ms: int = 0
