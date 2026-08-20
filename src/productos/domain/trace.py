from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TraceEventType(StrEnum):
    RUN_STARTED = "run.started"
    INTENT_CLASSIFIED = "intent.classified"
    WORKFLOW_SELECTED = "workflow.selected"
    PLAN_CREATED = "plan.created"
    WORKFLOW_STAGE_STARTED = "workflow.stage_started"
    WORKFLOW_STAGE_COMPLETED = "workflow.stage_completed"
    CONTEXT_BUILD_STARTED = "context.build_started"
    CONTEXT_BUILD_COMPLETED = "context.build_completed"
    MEMORY_SEARCH_STARTED = "memory.search_started"
    MEMORY_SEARCH_COMPLETED = "memory.search_completed"
    MEMORY_CANDIDATES_EXTRACTED = "memory.candidates_extracted"
    MEMORY_WRITE_COMPLETED = "memory.write_completed"
    RETRIEVAL_STARTED = "retrieval.started"
    RETRIEVAL_COMPLETED = "retrieval.completed"
    EVIDENCE_PACKET_CREATED = "evidence.packet_created"
    ARTIFACT_CREATED = "artifact.created"
    TOOL_SELECTED = "tool.selected"
    TOOL_PERMISSION_CHECKED = "tool.permission_checked"
    TOOL_CALL_STARTED = "tool.call_started"
    TOOL_CALL_COMPLETED = "tool.call_completed"
    TOOL_CALL_FAILED = "tool.call_failed"
    MODEL_STREAM_STARTED = "model.stream_started"
    MODEL_STREAM_COMPLETED = "model.stream_completed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


class TraceEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    event_type: TraceEventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    attributes: dict[str, Any] = Field(default_factory=dict)
