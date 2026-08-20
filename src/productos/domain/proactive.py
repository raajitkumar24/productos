from datetime import UTC, datetime, time
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from productos.domain.management import ConfidenceLevel, Significance


class ScheduleKind(StrEnum):
    DAILY_PRODUCT_BRIEF = "daily_product_brief"
    WEEKLY_LEADERSHIP_BRIEF = "weekly_leadership_brief"
    DECISION_REVIEW_SCAN = "decision_review_scan"
    RISK_SCAN = "risk_scan"


class ScheduleFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"


class ProactiveSchedule(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    user_id: UUID
    kind: ScheduleKind
    frequency: ScheduleFrequency
    enabled: bool = False
    timezone: str = "UTC"
    local_time: time = time(hour=8, minute=30)
    weekday: int | None = Field(default=None, ge=0, le=6)
    next_run_at: datetime
    last_run_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def weekly_requires_weekday(self) -> "ProactiveSchedule":
        if self.frequency == ScheduleFrequency.WEEKLY and self.weekday is None:
            raise ValueError("weekday is required for a weekly schedule")
        return self


class ScheduleCreate(BaseModel):
    kind: ScheduleKind
    frequency: ScheduleFrequency
    enabled: bool = False
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    local_time: time = time(hour=8, minute=30)
    weekday: int | None = Field(default=None, ge=0, le=6)
    next_run_at: datetime
    user_id: UUID | None = None
    tenant_id: UUID | None = None

    @model_validator(mode="after")
    def weekly_requires_weekday(self) -> "ScheduleCreate":
        if self.frequency == ScheduleFrequency.WEEKLY and self.weekday is None:
            raise ValueError("weekday is required for a weekly schedule")
        return self


class SchedulePatch(BaseModel):
    enabled: bool | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=100)
    local_time: time | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    next_run_at: datetime | None = None


class NotificationPreferences(BaseModel):
    tenant_id: UUID
    user_id: UUID
    enabled: bool = False
    in_app_enabled: bool = True
    daily_brief_enabled: bool = True
    weekly_brief_enabled: bool = True
    decision_reminders_enabled: bool = True
    risk_alerts_enabled: bool = True
    minimum_level: Significance = Significance.HIGH
    maximum_per_day: int = Field(default=3, ge=0, le=25)
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    timezone: str = "UTC"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NotificationPreferencesPatch(BaseModel):
    enabled: bool | None = None
    in_app_enabled: bool | None = None
    daily_brief_enabled: bool | None = None
    weekly_brief_enabled: bool | None = None
    decision_reminders_enabled: bool | None = None
    risk_alerts_enabled: bool | None = None
    minimum_level: Significance | None = None
    maximum_per_day: int | None = Field(default=None, ge=0, le=25)
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=100)


class ChangeSnapshot(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    user_id: UUID
    subject_type: str
    subject_id: str
    fingerprint: str
    state: dict[str, object]
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ChangeEvent(BaseModel):
    subject_type: str
    subject_id: str
    change_type: str
    summary: str
    evidence_ids: list[str]
    confidence: ConfidenceLevel
    level: Significance
    actionable: bool
    material: bool
    limitations: list[str]
    recommended_next_step: str | None = None


class NotificationStatus(StrEnum):
    UNREAD = "unread"
    READ = "read"
    DISMISSED = "dismissed"


class ProactiveNotification(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    user_id: UUID
    dedupe_key: str
    category: str
    title: str
    body: str
    level: Significance
    evidence_ids: list[str]
    confidence: ConfidenceLevel
    limitations: list[str]
    recommended_next_step: str
    related_artifact_id: UUID | None = None
    status: NotificationStatus = NotificationStatus.UNREAD
    delivery_channel: str = "in_app"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    read_at: datetime | None = None


class NotificationPatch(BaseModel):
    status: NotificationStatus


class DailyProductBrief(BaseModel):
    generated_at: datetime
    things_needing_attention: list[str]
    recent_wins: list[str]
    upcoming_decisions: list[str]
    material_changes: list[ChangeEvent]
    evidence_ids: list[str]
    evidence_limitations: list[str]


class SchedulerRunRequest(BaseModel):
    now: datetime | None = None
    force_kinds: list[ScheduleKind] = Field(default_factory=list)
    user_id: UUID | None = None
    tenant_id: UUID | None = None


class SchedulerRunResult(BaseModel):
    run_id: UUID
    started_at: datetime
    completed_at: datetime
    schedules_evaluated: int
    schedules_run: int
    artifacts_created: list[UUID]
    notifications_created: list[UUID]
    suppressed: list[str]
