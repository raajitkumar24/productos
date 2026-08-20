from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from productos.infrastructure.database import Base


class VectorStorage(TypeDecorator[list[float]]):
    """pgvector in PostgreSQL and JSON vectors in local SQLite."""

    impl = JSON
    cache_ok = True

    def __init__(self, dimension: int) -> None:
        super().__init__()
        self.dimension = dimension

    def load_dialect_impl(self, dialect: Dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dimension))
        return dialect.type_descriptor(JSON())


class OrganizationRow(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConversationRow(Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user_updated", "user_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    messages: Mapped[list["MessageRow"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="MessageRow.created_at",
    )


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    conversation: Mapped[ConversationRow] = relationship(back_populates="messages")


class WorkingSessionRow(Base):
    __tablename__ = "working_sessions"
    __table_args__ = (Index("ix_working_sessions_user_status", "user_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    open_questions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    hypotheses: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentRunRow(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    request: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    workflow: Mapped[str] = mapped_column(String(100), nullable=False)
    runtime_version: Mapped[str] = mapped_column(String(50), nullable=False)
    constitution_version: Mapped[str] = mapped_column(String(50), nullable=False)
    memory_policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    retrieval_policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    tool_contract_version: Mapped[str] = mapped_column(String(50), nullable=False)
    mcp_adapter_version: Mapped[str] = mapped_column(String(50), nullable=False)
    workflow_version: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_versions: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TraceEventRow(Base):
    __tablename__ = "trace_events"
    __table_args__ = (Index("ix_trace_events_run_occurred", "run_id", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class ToolCallRow(Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        Index("ix_tool_calls_run_started", "run_id", "started_at"),
        Index("ix_tool_calls_scope_status", "tenant_id", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    capability: Mapped[str] = mapped_column(String(200), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    result_count: Mapped[int | None] = mapped_column(nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)
    contract_version: Mapped[str] = mapped_column(String(50), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ArtifactRow(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        Index("ix_artifacts_scope_updated", "tenant_id", "user_id", "updated_at"),
        Index("ix_artifacts_scope_type", "tenant_id", "user_id", "artifact_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    structured_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rendered_content: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    workflow_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    workflow_version: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=False, index=True
    )
    working_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("working_sessions.id"), nullable=True, index=True
    )
    source_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    memory_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    model_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InitiativeRow(Base):
    __tablename__ = "initiatives"
    __table_args__ = (Index("ix_initiatives_scope_status", "tenant_id", "user_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    problem: Mapped[str] = mapped_column(Text, nullable=False)
    owner_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    objective_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    target_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    product_outcomes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    business_outcomes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    decision_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    jira_issue_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    dependency_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    health: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class OutcomeRow(Base):
    __tablename__ = "outcomes"
    __table_args__ = (Index("ix_outcomes_scope_status", "tenant_id", "user_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    outcome_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    baseline: Mapped[str | None] = mapped_column(Text, nullable=True)
    target: Mapped[str | None] = mapped_column(Text, nullable=True)
    current: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric: Mapped[str | None] = mapped_column(String(500), nullable=True)
    owner_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    initiative_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    attribution: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class CommitmentRow(Base):
    __tablename__ = "commitments"
    __table_args__ = (Index("ix_commitments_scope_status", "tenant_id", "user_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(500), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    initiative_id: Mapped[str | None] = mapped_column(
        ForeignKey("initiatives.id"), nullable=True, index=True
    )
    dependencies: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class ManagementSignalRow(Base):
    __tablename__ = "management_signals"
    __table_args__ = (
        Index("ix_management_signals_scope_status", "tenant_id", "user_id", "status"),
        Index("ix_management_signals_subject", "subject_type", "subject_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(50), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(500), nullable=False)
    epistemic_level: Mapped[str] = mapped_column(String(50), nullable=False)
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    derived_signal: Mapped[str | None] = mapped_column(Text, nullable=True)
    interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[str] = mapped_column(String(30), nullable=False)
    significance: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    time_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    time_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SignalCorrectionRow(Base):
    __tablename__ = "management_signal_corrections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    signal_id: Mapped[str] = mapped_column(
        ForeignKey("management_signals.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    prior_interpretation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AttentionSignalRow(Base):
    __tablename__ = "attention_signals"
    __table_args__ = (Index("ix_attention_scope_status", "tenant_id", "user_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    management_signal_id: Mapped[str] = mapped_column(
        ForeignKey("management_signals.id"), nullable=False, index=True
    )
    subject_type: Mapped[str] = mapped_column(String(50), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(500), nullable=False)
    level: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    why_surfaced: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[str] = mapped_column(String(30), nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    recommended_next_step: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProactiveScheduleRow(Base):
    __tablename__ = "proactive_schedules"
    __table_args__ = (
        Index("ix_proactive_schedules_due", "tenant_id", "user_id", "enabled", "next_run_at"),
        UniqueConstraint("tenant_id", "user_id", "kind", name="uq_proactive_schedule_scope_kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    local_time: Mapped[str] = mapped_column(String(20), nullable=False)
    weekday: Mapped[int | None] = mapped_column(nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NotificationPreferencesRow(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_notification_preferences_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(nullable=False)
    in_app_enabled: Mapped[bool] = mapped_column(nullable=False)
    daily_brief_enabled: Mapped[bool] = mapped_column(nullable=False)
    weekly_brief_enabled: Mapped[bool] = mapped_column(nullable=False)
    decision_reminders_enabled: Mapped[bool] = mapped_column(nullable=False)
    risk_alerts_enabled: Mapped[bool] = mapped_column(nullable=False)
    minimum_level: Mapped[str] = mapped_column(String(20), nullable=False)
    maximum_per_day: Mapped[int] = mapped_column(nullable=False)
    quiet_hours_start: Mapped[str | None] = mapped_column(String(20), nullable=True)
    quiet_hours_end: Mapped[str | None] = mapped_column(String(20), nullable=True)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChangeSnapshotRow(Base):
    __tablename__ = "change_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "subject_type",
            "subject_id",
            name="uq_change_snapshot_subject",
        ),
        Index("ix_change_snapshots_scope_observed", "tenant_id", "user_id", "observed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String(50), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(500), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProactiveNotificationRow(Base):
    __tablename__ = "proactive_notifications"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "dedupe_key", name="uq_notification_dedupe"),
        Index("ix_proactive_notifications_scope_status", "tenant_id", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    recommended_next_step: Mapped[str] = mapped_column(Text, nullable=False)
    related_artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifacts.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    delivery_channel: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MemoryRow(Base):
    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_user_type_status", "user_id", "memory_type", "status"),
        Index("ix_memories_user_key_status", "user_id", "memory_key", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    memory_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    importance: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provenance_type: Mapped[str] = mapped_column(String(30), nullable=False)
    memory_key: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MemoryRelationshipRow(Base):
    __tablename__ = "memory_relationships"
    __table_args__ = (
        UniqueConstraint(
            "from_memory_id",
            "to_memory_id",
            "relationship_type",
            name="uq_memory_relationship",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    from_memory_id: Mapped[str] = mapped_column(
        ForeignKey("memories.id"), nullable=False, index=True
    )
    to_memory_id: Mapped[str] = mapped_column(ForeignKey("memories.id"), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BeliefRow(Base):
    __tablename__ = "beliefs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memories.id"), nullable=False, unique=True, index=True
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    supporting_evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    contradicting_evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)


class DecisionRow(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    memory_id: Mapped[str | None] = mapped_column(
        ForeignKey("memories.id"), nullable=True, unique=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    problem: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    alternatives: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    rejected_alternatives: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    assumptions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    tradeoffs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    owner: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_trigger: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class KnowledgeItemRow(Base):
    __tablename__ = "knowledge_items"
    __table_args__ = (
        Index(
            "ix_knowledge_items_scope_source",
            "tenant_id",
            "user_id",
            "source_type",
            "source_id",
            "status",
        ),
        Index("ix_knowledge_items_scope_status", "tenant_id", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1_000), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    document_format: Mapped[str] = mapped_column(String(30), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(500), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(500), nullable=True)
    workspace: Mapped[str | None] = mapped_column(String(500), nullable=True)
    project: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    url: Mapped[str | None] = mapped_column(String(2_000), nullable=True)
    source_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    authority_score: Mapped[float] = mapped_column(Float, nullable=False)
    sensitivity: Mapped[str] = mapped_column(String(30), nullable=False)
    access_boundary: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    supersedes_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_items.id"), nullable=True, index=True
    )
    embedding_provider: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)
    chunks: Mapped[list["KnowledgeChunkRow"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="KnowledgeChunkRow.chunk_index",
    )


class KnowledgeChunkRow(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("knowledge_item_id", "chunk_index", name="uq_knowledge_chunk_index"),
        Index("ix_knowledge_chunks_scope", "tenant_id", "user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    knowledge_item_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_items.id"), nullable=False, index=True
    )
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VectorStorage(128), nullable=False)
    section_title: Mapped[str | None] = mapped_column(String(1_000), nullable=True)
    parent_section: Mapped[str | None] = mapped_column(String(1_000), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False)
    item: Mapped[KnowledgeItemRow] = relationship(back_populates="chunks")


class EvaluationRunRow(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        Index("ix_evaluation_runs_scope_created", "tenant_id", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    dataset_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    dataset_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    subject_model: Mapped[str] = mapped_column(String(300), nullable=False)
    judge_model: Mapped[str] = mapped_column(String(300), nullable=False)
    runtime_version: Mapped[str] = mapped_column(String(50), nullable=False)
    metrics_version: Mapped[str] = mapped_column(String(50), nullable=False)
    total_cases: Mapped[int] = mapped_column(nullable=False)
    passed_cases: Mapped[int] = mapped_column(nullable=False)
    failed_cases: Mapped[int] = mapped_column(nullable=False)
    error_cases: Mapped[int] = mapped_column(nullable=False)
    pass_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    limitation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cases: Mapped[list["EvaluationCaseRow"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class EvaluationCaseRow(Base):
    __tablename__ = "evaluation_cases"
    __table_args__ = (
        UniqueConstraint("evaluation_run_id", "external_id", name="uq_evaluation_case_external"),
        Index("ix_evaluation_cases_run_status", "evaluation_run_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    evaluation_run_id: Mapped[str] = mapped_column(
        ForeignKey("evaluation_runs.id"), nullable=False, index=True
    )
    agent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=True, index=True
    )
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    expected_behaviors: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    forbidden_behaviors: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    actual_output: Mapped[str] = mapped_column(Text, nullable=False)
    judgment: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    run: Mapped[EvaluationRunRow] = relationship(back_populates="cases")
