from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class InitiativeStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class HealthState(StrEnum):
    HEALTHY = "healthy"
    WATCH = "watch"
    AT_RISK = "at_risk"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class InitiativeHealthDimension(BaseModel):
    dimension: str
    state: HealthState
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel
    explanation: str


class Initiative(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    user_id: UUID
    name: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=20_000)
    problem: str = Field(default="", max_length=20_000)
    owner_ids: list[str] = Field(default_factory=list, max_length=50)
    objective_ids: list[str] = Field(default_factory=list, max_length=50)
    status: InitiativeStatus = InitiativeStatus.PROPOSED
    start_date: date | None = None
    target_date: date | None = None
    product_outcomes: list[str] = Field(default_factory=list)
    business_outcomes: list[str] = Field(default_factory=list)
    decision_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    jira_issue_ids: list[str] = Field(default_factory=list)
    dependency_ids: list[str] = Field(default_factory=list)
    health: list[InitiativeHealthDimension] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InitiativeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=20_000)
    problem: str = Field(default="", max_length=20_000)
    owner_ids: list[str] = Field(default_factory=list, max_length=50)
    objective_ids: list[str] = Field(default_factory=list, max_length=50)
    status: InitiativeStatus = InitiativeStatus.PROPOSED
    start_date: date | None = None
    target_date: date | None = None
    product_outcomes: list[str] = Field(default_factory=list)
    business_outcomes: list[str] = Field(default_factory=list)
    decision_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    jira_issue_ids: list[str] = Field(default_factory=list)
    dependency_ids: list[str] = Field(default_factory=list)
    user_id: UUID | None = None
    tenant_id: UUID | None = None


class OutcomeType(StrEnum):
    PRODUCT = "product"
    CUSTOMER = "customer"
    BUSINESS = "business"


class OutcomeStatus(StrEnum):
    PLANNED = "planned"
    MEASURING = "measuring"
    ACHIEVED = "achieved"
    MISSED = "missed"
    UNKNOWN = "unknown"


class AttributionType(StrEnum):
    DIRECT = "direct"
    CONTRIBUTING = "contributing"
    CORRELATED = "correlated"
    UNKNOWN = "unknown"


class Outcome(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    user_id: UUID
    name: str = Field(min_length=1, max_length=500)
    outcome_type: OutcomeType
    baseline: str | None = None
    target: str | None = None
    current: str | None = None
    metric: str | None = None
    owner_ids: list[str] = Field(default_factory=list)
    initiative_ids: list[UUID] = Field(default_factory=list)
    status: OutcomeStatus = OutcomeStatus.PLANNED
    attribution: AttributionType = AttributionType.UNKNOWN
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OutcomeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    outcome_type: OutcomeType
    baseline: str | None = None
    target: str | None = None
    current: str | None = None
    metric: str | None = None
    owner_ids: list[str] = Field(default_factory=list)
    initiative_ids: list[UUID] = Field(default_factory=list)
    status: OutcomeStatus = OutcomeStatus.PLANNED
    attribution: AttributionType = AttributionType.UNKNOWN
    evidence_ids: list[str] = Field(default_factory=list)
    user_id: UUID | None = None
    tenant_id: UUID | None = None


class CommitmentStatus(StrEnum):
    PROPOSED = "proposed"
    COMMITTED = "committed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    AT_RISK = "at_risk"
    MISSED = "missed"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class CommitmentHistory(BaseModel):
    changed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    prior_due_at: datetime | None = None
    new_due_at: datetime | None = None
    prior_status: CommitmentStatus | None = None
    new_status: CommitmentStatus | None = None
    reason: str | None = None
    source: str


class Commitment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    user_id: UUID
    description: str = Field(min_length=1, max_length=20_000)
    owner_id: str
    source: str
    due_at: datetime | None = None
    status: CommitmentStatus = CommitmentStatus.PROPOSED
    initiative_id: UUID | None = None
    dependencies: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    history: list[CommitmentHistory] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CommitmentCreate(BaseModel):
    description: str = Field(min_length=1, max_length=20_000)
    owner_id: str = Field(min_length=1, max_length=500)
    source: str = Field(min_length=1, max_length=500)
    due_at: datetime | None = None
    status: CommitmentStatus = CommitmentStatus.PROPOSED
    initiative_id: UUID | None = None
    dependencies: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    user_id: UUID | None = None
    tenant_id: UUID | None = None


class CommitmentPatch(BaseModel):
    due_at: datetime | None = None
    status: CommitmentStatus | None = None
    reason: str | None = Field(default=None, max_length=5_000)
    source: str = Field(default="user_correction", max_length=500)

    @model_validator(mode="after")
    def reason_for_date_change(self) -> "CommitmentPatch":
        if "due_at" in self.model_fields_set and not self.reason:
            raise ValueError("A reason is required when changing a commitment date")
        return self


class EpistemicLevel(StrEnum):
    OBSERVATION = "observation"
    DERIVED_SIGNAL = "derived_signal"
    INTERPRETATION = "interpretation"
    RECOMMENDATION = "recommendation"


class SignalType(StrEnum):
    STRENGTH = "strength"
    RISK = "risk"
    COACHING_OPPORTUNITY = "coaching_opportunity"
    DECISION_REVIEW = "decision_review"
    EXECUTION_RISK = "execution_risk"
    OUTCOME_GAP = "outcome_gap"
    LEARNING_SIGNAL = "learning_signal"
    DEPENDENCY_RISK = "dependency_risk"


class Significance(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SignalStatus(StrEnum):
    ACTIVE = "active"
    CONFIRMED = "confirmed"
    DISAGREED = "disagreed"
    DISMISSED = "dismissed"
    OUTDATED = "outdated"


class ManagementSignal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    user_id: UUID
    signal_type: SignalType
    subject_type: str
    subject_id: str
    epistemic_level: EpistemicLevel
    observation: str
    derived_signal: str | None = None
    interpretation: str | None = None
    recommendation: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel
    significance: Significance
    time_window_start: datetime
    time_window_end: datetime
    limitations: list[str] = Field(default_factory=list)
    status: SignalStatus = SignalStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CorrectionAction(StrEnum):
    CONFIRM = "confirm"
    ADD_CONTEXT = "add_context"
    DISAGREE = "disagree"
    DISMISS = "dismiss"
    MARK_OUTDATED = "mark_outdated"


class SignalCorrection(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    signal_id: UUID
    user_id: UUID
    action: CorrectionAction
    context: str | None = Field(default=None, max_length=10_000)
    prior_interpretation: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SignalCorrectionCreate(BaseModel):
    action: CorrectionAction
    context: str | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def context_when_needed(self) -> "SignalCorrectionCreate":
        if (
            self.action in {CorrectionAction.ADD_CONTEXT, CorrectionAction.DISAGREE}
            and not self.context
        ):
            raise ValueError("Context is required for this correction")
        return self


class DecisionDebt(BaseModel):
    decision_id: UUID
    title: str
    debt_type: str
    evidence_ids: list[str] = Field(default_factory=list)
    severity: Significance
    next_review_action: str
    limitation: str | None = None


class PMIntelligenceProfile(BaseModel):
    pm_id: str
    responsibilities: list[str]
    initiatives: list[Initiative]
    outcomes: list[Outcome]
    commitments: list[Commitment]
    important_decisions: list[dict[str, Any]]
    observed_strengths: list[ManagementSignal]
    coaching_opportunities: list[ManagementSignal]
    risks: list[ManagementSignal]
    limitations: list[str]
    evidence_window_start: datetime
    evidence_window_end: datetime


class OneOnOneBrief(BaseModel):
    pm_id: str
    what_changed: list[str]
    wins_to_recognize: list[str]
    things_to_understand: list[str]
    decisions_to_review: list[str]
    coaching_opportunities: list[str]
    suggested_questions: list[str]
    evidence_ids: list[str]
    evidence_limitations: list[str]


class PMReview(BaseModel):
    pm_id: str
    observations: list[str]
    interpretations: list[str]
    product_craft: list[str]
    outcomes: list[str]
    strengths: list[str]
    coaching_questions: list[str]
    evidence_ids: list[str]
    evidence_limitations: list[str]


class WeeklyManagementReview(BaseModel):
    outcomes: list[str]
    major_progress: list[str]
    important_decisions: list[str]
    initiative_risks: list[str]
    commitment_changes: list[str]
    product_quality_concerns: list[str]
    customer_signals: list[str]
    pm_wins: list[str]
    coaching_opportunities: list[str]
    leadership_decisions_required: list[str]
    evidence_ids: list[str]
    evidence_limitations: list[str]


class PortfolioReview(BaseModel):
    shared_dependencies: list[str]
    launch_collisions: list[str]
    unowned_dependencies: list[str]
    missing_outcomes: list[str]
    weak_customer_evidence: list[str]
    repeated_target_movement: list[str]
    unresolved_decisions: list[str]
    spec_execution_divergence: list[str]
    missing_instrumentation: list[str]
    critical_assumptions: list[str]
    evidence_ids: list[str]
    evidence_limitations: list[str]


class AttentionSignal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    user_id: UUID
    management_signal_id: UUID
    subject_type: str
    subject_id: str
    level: Significance
    why_surfaced: str
    evidence_ids: list[str]
    confidence: ConfidenceLevel
    limitations: list[str]
    recommended_next_step: str
    status: SignalStatus = SignalStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ManagementWorkflowRequest(BaseModel):
    pm_id: str | None = Field(default=None, max_length=500)
    weeks: int = Field(default=4, ge=1, le=52)
    user_id: UUID | None = None
    tenant_id: UUID | None = None

    @property
    def window_start(self) -> datetime:
        return datetime.now(UTC) - timedelta(weeks=self.weeks)
