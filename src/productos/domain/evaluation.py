from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class EvaluationRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvaluationCaseStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class RepresentativeEvaluationCase(BaseModel):
    external_id: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    input_text: str = Field(min_length=1, max_length=50_000)
    expected_behaviors: list[str] = Field(min_length=1, max_length=30)
    forbidden_behaviors: list[str] = Field(default_factory=list, max_length=30)


class EvaluationRunCreate(BaseModel):
    dataset_name: str = Field(min_length=1, max_length=200)
    dataset_version: str = Field(min_length=1, max_length=100)
    cases: list[RepresentativeEvaluationCase] = Field(min_length=1, max_length=20)
    user_id: UUID | None = None
    tenant_id: UUID | None = None

    @model_validator(mode="after")
    def unique_case_ids(self) -> "EvaluationRunCreate":
        identifiers = [item.external_id for item in self.cases]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Evaluation case external_id values must be unique")
        return self


class EvaluationJudgment(BaseModel):
    score: int = Field(ge=1, le=5)
    criteria: dict[str, int]
    critical_failure: bool
    reasoning_summary: str = Field(max_length=4_000)
    missing_elements: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_criteria_scores(self) -> "EvaluationJudgment":
        if any(value < 1 or value > 5 for value in self.criteria.values()):
            raise ValueError("Judgment criteria scores must be between 1 and 5")
        return self


class EvaluationCaseResult(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    evaluation_run_id: UUID
    agent_run_id: UUID | None = None
    external_id: str
    category: str
    input_text: str
    expected_behaviors: list[str]
    forbidden_behaviors: list[str]
    actual_output: str
    judgment: EvaluationJudgment | None = None
    status: EvaluationCaseStatus
    error_code: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvaluationRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    user_id: UUID
    dataset_name: str
    dataset_version: str
    status: EvaluationRunStatus = EvaluationRunStatus.RUNNING
    subject_model: str
    judge_model: str
    runtime_version: str
    metrics_version: str
    total_cases: int
    passed_cases: int = 0
    failed_cases: int = 0
    error_cases: int = 0
    pass_rate: float | None = None
    limitation: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class EvaluationRunDetail(BaseModel):
    run: EvaluationRun
    cases: list[EvaluationCaseResult]
