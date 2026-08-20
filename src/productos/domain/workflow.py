from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

from productos.domain.knowledge import EvidenceItem


class WorkflowName(StrEnum):
    DEEP_RESEARCH = "deep_research"
    PRODUCT_STRATEGY = "product_strategy"
    PRODUCT_REVIEW = "product_review"
    SPEC_EXECUTION = "spec_execution"
    EXPERIMENT_DESIGN = "experiment_design"
    DECISION_MEMO = "decision_memo"
    PREPARE_ONE_ON_ONE = "prepare_one_on_one"
    PM_REVIEW = "pm_review"
    WEEKLY_MANAGEMENT_REVIEW = "weekly_management_review"
    PORTFOLIO_REVIEW = "portfolio_review"
    DAILY_PRODUCT_BRIEF = "daily_product_brief"
    WEEKLY_PRODUCT_LEADERSHIP_BRIEF = "weekly_product_leadership_brief"


class ArtifactType(StrEnum):
    RESEARCH_REPORT = "research_report"
    STRATEGY_MEMO = "strategy_memo"
    PRODUCT_REVIEW = "product_review"
    SPEC_EXECUTION_REVIEW = "spec_execution_review"
    EXPERIMENT_PLAN = "experiment_plan"
    DECISION_MEMO = "decision_memo"
    MANAGEMENT_BRIEF = "management_brief"
    PRODUCT_BRIEF = "product_brief"


class ArtifactStatus(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    PUBLISHED = "published"


class WorkflowStage(BaseModel):
    name: str
    required: bool = True


class WorkflowDefinition(BaseModel):
    name: WorkflowName
    version: str
    supported_intents: list[str]
    required_capabilities: list[str] = Field(default_factory=list)
    optional_capabilities: list[str] = Field(default_factory=list)
    stages: list[WorkflowStage]
    artifact_type: ArtifactType
    evaluation_profile: str
    max_iterations: int = Field(ge=1, le=20)


class WorkflowStageState(BaseModel):
    name: str
    status: str
    summary: str


class WorkflowExecution(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    definition_name: WorkflowName
    definition_version: str
    status: str = "running"
    stages: list[WorkflowStageState] = Field(default_factory=list)
    iterations: int = 1
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class ResearchQuestion(BaseModel):
    question: str
    importance: str
    required_sources: list[str]
    status: str
    evidence_ids: list[str] = Field(default_factory=list)
    answer: str | None = None
    confidence: str = "unknown"


class ResearchCoverage(BaseModel):
    dimension: str
    status: str
    evidence_ids: list[str] = Field(default_factory=list)
    limitation: str | None = None


class EvidenceLedger(BaseModel):
    topic: str
    supporting: list[EvidenceItem] = Field(default_factory=list)
    contradicting: list[EvidenceItem] = Field(default_factory=list)
    neutral: list[EvidenceItem] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    confidence: str = "unknown"


class Assumption(BaseModel):
    statement: str
    category: str
    confidence: str
    criticality: str
    evidence_ids: list[str] = Field(default_factory=list)
    validation_status: str = "unvalidated"


class StrategyOption(BaseModel):
    name: str
    description: str
    advantages: list[str]
    tradeoffs: list[str]
    reversibility: str
    evidence_ids: list[str] = Field(default_factory=list)


class ReviewSeverity(StrEnum):
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"
    QUESTION = "question"
    SUGGESTION = "suggestion"


class ReviewFinding(BaseModel):
    rubric_item: str
    severity: ReviewSeverity
    observation: str
    evidence_excerpt: str | None = None
    recommendation: str


class ExperimentDesign(BaseModel):
    problem: str
    hypothesis: str
    mechanism: str
    target_population: str
    treatment: str
    control: str
    primary_metric: str
    secondary_metrics: list[str]
    guardrails: list[str]
    segmentation: list[str]
    instrumentation: list[str]
    risks: list[str]
    decision_rule: str
    expected_learning: str
    agent_configuration: dict[str, str | None] = Field(default_factory=dict)


class Artifact(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    user_id: UUID
    artifact_type: ArtifactType
    title: str
    structured_data: dict[str, Any]
    rendered_content: str
    workflow_id: UUID
    workflow_name: WorkflowName
    workflow_version: str
    agent_run_id: UUID
    working_session_id: UUID | None = None
    source_ids: list[str] = Field(default_factory=list)
    memory_ids: list[str] = Field(default_factory=list)
    model_metadata: dict[str, Any] = Field(default_factory=dict)
    status: ArtifactStatus = ArtifactStatus.DRAFT
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WorkflowExecuteRequest(BaseModel):
    workflow: WorkflowName
    objective: str = Field(min_length=1, max_length=20_000)
    title: str | None = Field(default=None, max_length=500)
    source_text: str | None = Field(default=None, max_length=200_000)
    page_id: str | None = Field(default=None, max_length=500)
    projects: list[str] = Field(default_factory=list, max_length=20)
    working_session_id: UUID | None = None
    workspace_id: str | None = Field(default=None, max_length=500)
    user_id: UUID | None = None
    tenant_id: UUID | None = None
    context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def required_inputs(self) -> "WorkflowExecuteRequest":
        if self.workflow == WorkflowName.PRODUCT_REVIEW and not self.source_text:
            raise ValueError("product_review requires source_text")
        if self.workflow == WorkflowName.SPEC_EXECUTION and not self.page_id:
            raise ValueError("spec_execution requires page_id")
        return self


class WorkflowResult(BaseModel):
    execution: WorkflowExecution
    artifact: Artifact
    evidence_ledger: EvidenceLedger
