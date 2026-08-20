from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from productos.application.ports import TraceRepository
from productos.application.repositories import (
    AgentRunRepository,
    ArtifactRepository,
    DecisionRepository,
    ManagementRepository,
)
from productos.config import Settings
from productos.domain.agent import AgentState, RunStatus
from productos.domain.management import (
    AttentionSignal,
    Commitment,
    CommitmentCreate,
    CommitmentHistory,
    CommitmentPatch,
    CommitmentStatus,
    ConfidenceLevel,
    CorrectionAction,
    DecisionDebt,
    EpistemicLevel,
    HealthState,
    Initiative,
    InitiativeCreate,
    InitiativeHealthDimension,
    ManagementSignal,
    OneOnOneBrief,
    Outcome,
    OutcomeCreate,
    OutcomeStatus,
    PMIntelligenceProfile,
    PMReview,
    PortfolioReview,
    SignalCorrection,
    SignalCorrectionCreate,
    SignalStatus,
    SignalType,
    Significance,
    WeeklyManagementReview,
)
from productos.domain.memory import Decision
from productos.domain.trace import TraceEvent, TraceEventType
from productos.domain.workflow import Artifact, ArtifactType, WorkflowName

HEALTH_DIMENSIONS = (
    "problem_evidence",
    "outcome_clarity",
    "strategic_alignment",
    "decision_quality",
    "execution_progress",
    "dependency_health",
    "measurement_readiness",
    "learning_velocity",
)


class ManagementService:
    def __init__(
        self,
        repository: ManagementRepository,
        decisions: DecisionRepository,
        artifacts: ArtifactRepository,
        runs: AgentRunRepository,
        traces: TraceRepository,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._decisions = decisions
        self._artifacts = artifacts
        self._runs = runs
        self._traces = traces
        self._settings = settings

    async def create_initiative(
        self, request: InitiativeCreate, tenant_id: UUID, user_id: UUID
    ) -> Initiative:
        initiative = Initiative(
            **request.model_dump(exclude={"tenant_id", "user_id"}),
            tenant_id=tenant_id,
            user_id=user_id,
        )
        initiative.health = self._health(initiative, [], [])
        return await self._repository.create_initiative(initiative)

    async def list_initiatives(self, tenant_id: UUID, user_id: UUID) -> list[Initiative]:
        initiatives = await self._repository.list_initiatives(tenant_id, user_id)
        outcomes = await self._repository.list_outcomes(tenant_id, user_id)
        commitments = await self._repository.list_commitments(tenant_id, user_id)
        for initiative in initiatives:
            initiative.health = self._health(initiative, outcomes, commitments)
            await self._repository.update_initiative(initiative)
        return initiatives

    async def get_initiative(
        self, initiative_id: UUID, tenant_id: UUID, user_id: UUID
    ) -> Initiative | None:
        initiative = await self._repository.get_initiative(initiative_id, tenant_id, user_id)
        if not initiative:
            return None
        outcomes = await self._repository.list_outcomes(tenant_id, user_id)
        commitments = await self._repository.list_commitments(tenant_id, user_id)
        initiative.health = self._health(initiative, outcomes, commitments)
        return initiative

    async def create_outcome(
        self, request: OutcomeCreate, tenant_id: UUID, user_id: UUID
    ) -> Outcome:
        outcome = Outcome(
            **request.model_dump(exclude={"tenant_id", "user_id"}),
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return await self._repository.create_outcome(outcome)

    async def create_commitment(
        self, request: CommitmentCreate, tenant_id: UUID, user_id: UUID
    ) -> Commitment:
        commitment = Commitment(
            **request.model_dump(exclude={"tenant_id", "user_id"}),
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return await self._repository.create_commitment(commitment)

    async def patch_commitment(
        self,
        commitment_id: UUID,
        request: CommitmentPatch,
        tenant_id: UUID,
        user_id: UUID,
    ) -> Commitment | None:
        commitment = await self._repository.get_commitment(commitment_id, tenant_id, user_id)
        if not commitment:
            return None
        prior_due = commitment.due_at
        prior_status = commitment.status
        if "due_at" in request.model_fields_set:
            commitment.due_at = request.due_at
        if request.status is not None:
            commitment.status = request.status
        commitment.history.append(
            CommitmentHistory(
                prior_due_at=prior_due,
                new_due_at=commitment.due_at,
                prior_status=prior_status,
                new_status=commitment.status,
                reason=request.reason,
                source=request.source,
            )
        )
        commitment.updated_at = datetime.now(UTC)
        return await self._repository.update_commitment(commitment)

    async def refresh_intelligence(
        self, tenant_id: UUID, user_id: UUID
    ) -> tuple[list[ManagementSignal], list[AttentionSignal]]:
        initiatives = await self.list_initiatives(tenant_id, user_id)
        outcomes = await self._repository.list_outcomes(tenant_id, user_id)
        commitments = await self._repository.list_commitments(tenant_id, user_id)
        signals = self._signals(initiatives, outcomes, commitments, tenant_id, user_id)
        current_fingerprints = {
            (item.signal_type, item.subject_id, item.observation) for item in signals
        }
        for previous in await self._repository.list_signals(tenant_id, user_id):
            fingerprint = (
                previous.signal_type,
                previous.subject_id,
                previous.observation,
            )
            if previous.status == SignalStatus.ACTIVE and fingerprint not in current_fingerprints:
                previous.status = SignalStatus.OUTDATED
                previous.limitations.append(
                    "The underlying condition was not present in the latest deterministic refresh."
                )
                previous.updated_at = datetime.now(UTC)
                await self._repository.update_signal(previous)
        stored = await self._repository.replace_signals(tenant_id, user_id, signals)
        active = [item for item in stored if item.status == SignalStatus.ACTIVE]
        attention = [
            AttentionSignal(
                tenant_id=tenant_id,
                user_id=user_id,
                management_signal_id=item.id,
                subject_type=item.subject_type,
                subject_id=item.subject_id,
                level=item.significance,
                why_surfaced=item.derived_signal or item.observation,
                evidence_ids=item.evidence_ids,
                confidence=item.confidence,
                limitations=item.limitations,
                recommended_next_step=item.recommendation
                or "Review the underlying evidence and add context.",
            )
            for item in active
            if item.significance in {Significance.CRITICAL, Significance.HIGH}
        ]
        stored_attention = await self._repository.replace_attention(tenant_id, user_id, attention)
        return stored, stored_attention

    async def correct_signal(
        self,
        signal_id: UUID,
        request: SignalCorrectionCreate,
        tenant_id: UUID,
        user_id: UUID,
    ) -> tuple[ManagementSignal, SignalCorrection] | None:
        signal = await self._repository.get_signal(signal_id, tenant_id, user_id)
        if not signal:
            return None
        correction = SignalCorrection(
            signal_id=signal.id,
            user_id=user_id,
            action=request.action,
            context=request.context,
            prior_interpretation=signal.interpretation,
        )
        status_map = {
            CorrectionAction.CONFIRM: SignalStatus.CONFIRMED,
            CorrectionAction.DISAGREE: SignalStatus.DISAGREED,
            CorrectionAction.DISMISS: SignalStatus.DISMISSED,
            CorrectionAction.MARK_OUTDATED: SignalStatus.OUTDATED,
        }
        if request.action in status_map:
            signal.status = status_map[request.action]
        if request.action == CorrectionAction.ADD_CONTEXT:
            signal.interpretation = (
                f"{signal.interpretation or ''}\nManager context: {request.context}"
            ).strip()
            signal.limitations.append("Interpretation includes manager-provided context.")
        if request.action == CorrectionAction.DISAGREE:
            signal.limitations.append(f"Manager disagreed: {request.context}")
        signal.updated_at = datetime.now(UTC)
        await self._repository.add_correction(correction)
        await self._repository.update_signal(signal)
        return signal, correction

    async def attention(self, tenant_id: UUID, user_id: UUID) -> list[AttentionSignal]:
        signals = await self._repository.list_signals(tenant_id, user_id)
        active_ids = {item.id for item in signals if item.status == SignalStatus.ACTIVE}
        return [
            item
            for item in await self._repository.list_attention(tenant_id, user_id)
            if item.management_signal_id in active_ids
        ]

    async def profile(
        self, pm_id: str, tenant_id: UUID, user_id: UUID, window_start: datetime
    ) -> PMIntelligenceProfile:
        initiatives = [
            item
            for item in await self.list_initiatives(tenant_id, user_id)
            if pm_id in item.owner_ids
        ]
        ids = {item.id for item in initiatives}
        outcomes = [
            item
            for item in await self._repository.list_outcomes(tenant_id, user_id)
            if pm_id in item.owner_ids or ids.intersection(item.initiative_ids)
        ]
        commitments = [
            item
            for item in await self._repository.list_commitments(tenant_id, user_id)
            if item.owner_id == pm_id
        ]
        decisions = await self._decisions.list(user_id)
        decision_ids = {value for item in initiatives for value in item.decision_ids}
        relevant_decisions = [item for item in decisions if str(item.id) in decision_ids]
        signals, _ = await self.refresh_intelligence(tenant_id, user_id)
        relevant_signals = [
            item
            for item in signals
            if (item.subject_type == "pm" and item.subject_id == pm_id)
            or (item.subject_type == "initiative" and item.subject_id in {str(v) for v in ids})
        ]
        limitations = []
        if not initiatives:
            limitations.append("No initiatives are explicitly assigned to this PM in ProductOS.")
        if not outcomes:
            limitations.append(
                "No linked outcome records were found; outcome assessment is unavailable."
            )
        limitations.append(
            "This profile is an evidence view, not an employee score or performance rating."
        )
        return PMIntelligenceProfile(
            pm_id=pm_id,
            responsibilities=[item.name for item in initiatives],
            initiatives=initiatives,
            outcomes=outcomes,
            commitments=commitments,
            important_decisions=[self._decision_summary(item) for item in relevant_decisions],
            observed_strengths=[
                item for item in relevant_signals if item.signal_type == SignalType.STRENGTH
            ],
            coaching_opportunities=[
                item
                for item in relevant_signals
                if item.signal_type == SignalType.COACHING_OPPORTUNITY
            ],
            risks=[
                item
                for item in relevant_signals
                if item.signal_type not in {SignalType.STRENGTH, SignalType.COACHING_OPPORTUNITY}
            ],
            limitations=limitations,
            evidence_window_start=window_start,
            evidence_window_end=datetime.now(UTC),
        )

    async def one_on_one(
        self, pm_id: str, tenant_id: UUID, user_id: UUID, window_start: datetime
    ) -> tuple[OneOnOneBrief, Artifact]:
        profile = await self.profile(pm_id, tenant_id, user_id, window_start)
        debt = await self.decision_debt(user_id)
        brief = OneOnOneBrief(
            pm_id=pm_id,
            what_changed=[
                f"{item.name}: {item.status}"
                for item in profile.initiatives
                if item.updated_at >= window_start
            ],
            wins_to_recognize=[item.observation for item in profile.observed_strengths],
            things_to_understand=[item.observation for item in profile.risks],
            decisions_to_review=[
                item.title
                for item in debt
                if str(item.decision_id)
                in {
                    value for initiative in profile.initiatives for value in initiative.decision_ids
                }
            ],
            coaching_opportunities=[
                item.interpretation or item.observation for item in profile.coaching_opportunities
            ],
            suggested_questions=self._questions(profile),
            evidence_ids=self._profile_evidence_ids(profile),
            evidence_limitations=profile.limitations,
        )
        artifact = await self._brief_artifact(
            WorkflowName.PREPARE_ONE_ON_ONE,
            f"1:1 preparation: {pm_id}",
            brief.model_dump(mode="json"),
            tenant_id,
            user_id,
        )
        return brief, artifact

    async def pm_review(
        self, pm_id: str, tenant_id: UUID, user_id: UUID, window_start: datetime
    ) -> tuple[PMReview, Artifact]:
        profile = await self.profile(pm_id, tenant_id, user_id, window_start)
        review = PMReview(
            pm_id=pm_id,
            observations=[
                item.observation
                for item in [
                    *profile.observed_strengths,
                    *profile.risks,
                    *profile.coaching_opportunities,
                ]
            ],
            interpretations=[item.interpretation for item in profile.risks if item.interpretation],
            product_craft=[item.observation for item in profile.observed_strengths],
            outcomes=[
                f"{item.name}: {item.status}; attribution {item.attribution}"
                for item in profile.outcomes
            ],
            strengths=[item.observation for item in profile.observed_strengths],
            coaching_questions=self._questions(profile),
            evidence_ids=self._profile_evidence_ids(profile),
            evidence_limitations=profile.limitations,
        )
        artifact = await self._brief_artifact(
            WorkflowName.PM_REVIEW,
            f"PM evidence review: {pm_id}",
            review.model_dump(mode="json"),
            tenant_id,
            user_id,
        )
        return review, artifact

    async def weekly_review(
        self,
        tenant_id: UUID,
        user_id: UUID,
        window_start: datetime,
        workflow: WorkflowName = WorkflowName.WEEKLY_MANAGEMENT_REVIEW,
        title: str = "Weekly product leadership review",
    ) -> tuple[WeeklyManagementReview, Artifact]:
        initiatives = await self.list_initiatives(tenant_id, user_id)
        outcomes = await self._repository.list_outcomes(tenant_id, user_id)
        commitments = await self._repository.list_commitments(tenant_id, user_id)
        signals, _ = await self.refresh_intelligence(tenant_id, user_id)
        active = [item for item in signals if item.status == SignalStatus.ACTIVE]
        review = WeeklyManagementReview(
            outcomes=[
                f"{item.name}: {item.status}; attribution {item.attribution}" for item in outcomes
            ],
            major_progress=[
                f"{item.name}: {item.status}"
                for item in initiatives
                if item.updated_at >= window_start
            ],
            important_decisions=[
                item.title
                for item in await self._decisions.list(user_id)
                if item.updated_at >= window_start
            ],
            initiative_risks=[
                item.observation
                for item in active
                if item.signal_type
                in {SignalType.RISK, SignalType.EXECUTION_RISK, SignalType.DEPENDENCY_RISK}
            ],
            commitment_changes=[
                item.description for item in commitments if item.updated_at >= window_start
            ],
            product_quality_concerns=[],
            customer_signals=[],
            pm_wins=[
                item.observation for item in active if item.signal_type == SignalType.STRENGTH
            ],
            coaching_opportunities=[
                item.interpretation or item.observation
                for item in active
                if item.signal_type == SignalType.COACHING_OPPORTUNITY
            ],
            leadership_decisions_required=[
                item.recommendation
                for item in active
                if item.significance in {Significance.HIGH, Significance.CRITICAL}
                and item.recommendation
            ],
            evidence_ids=sorted(
                {evidence for item in active for evidence in item.evidence_ids}
                | {f"initiative:{item.id}" for item in initiatives}
            ),
            evidence_limitations=[
                "Only ProductOS records within the selected evidence window are included."
            ],
        )
        artifact = await self._brief_artifact(
            workflow,
            title,
            review.model_dump(mode="json"),
            tenant_id,
            user_id,
        )
        return review, artifact

    async def portfolio_review(
        self, tenant_id: UUID, user_id: UUID
    ) -> tuple[PortfolioReview, Artifact]:
        initiatives = await self.list_initiatives(tenant_id, user_id)
        outcomes = await self._repository.list_outcomes(tenant_id, user_id)
        commitments = await self._repository.list_commitments(tenant_id, user_id)
        dependency_map: dict[str, list[str]] = defaultdict(list)
        for item in initiatives:
            for dependency in item.dependency_ids:
                dependency_map[dependency].append(item.name)
        outcome_initiatives = {value for item in outcomes for value in item.initiative_ids}
        review = PortfolioReview(
            shared_dependencies=[
                f"{key}: {', '.join(values)}"
                for key, values in dependency_map.items()
                if len(values) > 1
            ],
            launch_collisions=self._launch_collisions(initiatives),
            unowned_dependencies=[
                key
                for key, values in dependency_map.items()
                if key not in {str(item.id) for item in initiatives}
            ],
            missing_outcomes=[
                item.name
                for item in initiatives
                if item.id not in outcome_initiatives
                and not item.product_outcomes
                and not item.business_outcomes
            ],
            weak_customer_evidence=[item.name for item in initiatives if not item.evidence_ids],
            repeated_target_movement=[
                item.description
                for item in commitments
                if len(
                    [
                        history
                        for history in item.history
                        if history.prior_due_at != history.new_due_at
                    ]
                )
                >= 2
            ],
            unresolved_decisions=[
                item.title
                for item in await self._decisions.list(user_id)
                if item.status in {"proposed", "under_review"}
            ],
            spec_execution_divergence=[],
            missing_instrumentation=[item.name for item in outcomes if not item.metric],
            critical_assumptions=[],
            evidence_ids=[f"initiative:{item.id}" for item in initiatives],
            evidence_limitations=[
                "Portfolio signals use documented ProductOS records; "
                "inaccessible systems remain unknown."
            ],
        )
        artifact = await self._brief_artifact(
            WorkflowName.PORTFOLIO_REVIEW,
            "Portfolio intelligence review",
            review.model_dump(mode="json"),
            tenant_id,
            user_id,
        )
        return review, artifact

    async def decision_debt(self, user_id: UUID) -> list[DecisionDebt]:
        now = datetime.now(UTC)
        debt = []
        for decision in await self._decisions.list(user_id):
            if decision.review_at and decision.review_at <= now:
                debt.append(
                    DecisionDebt(
                        decision_id=decision.id,
                        title=decision.title,
                        debt_type="review_due",
                        evidence_ids=decision.evidence,
                        severity=Significance.HIGH,
                        next_review_action=(
                            "Review the decision against current evidence and outcomes."
                        ),
                    )
                )
            if decision.status == "accepted" and not decision.validation_plan:
                debt.append(
                    DecisionDebt(
                        decision_id=decision.id,
                        title=decision.title,
                        debt_type="validation_missing",
                        evidence_ids=decision.evidence,
                        severity=Significance.MEDIUM,
                        next_review_action="Define a validation plan and outcome measure.",
                    )
                )
        return debt

    @staticmethod
    def _health(
        initiative: Initiative, outcomes: list[Outcome], commitments: list[Commitment]
    ) -> list[InitiativeHealthDimension]:
        linked_outcomes = [item for item in outcomes if initiative.id in item.initiative_ids]
        linked_commitments = [item for item in commitments if item.initiative_id == initiative.id]
        risky_commitments = [
            item
            for item in linked_commitments
            if item.status in {CommitmentStatus.AT_RISK, CommitmentStatus.MISSED}
        ]
        values: dict[str, tuple[HealthState, list[str], ConfidenceLevel, str]] = {
            "problem_evidence": (
                HealthState.HEALTHY,
                initiative.evidence_ids,
                ConfidenceLevel.HIGH,
                "Problem evidence is linked.",
            )
            if initiative.evidence_ids
            else (
                HealthState.UNKNOWN,
                [],
                ConfidenceLevel.UNKNOWN,
                "No documented problem evidence is linked.",
            ),
            "outcome_clarity": (
                HealthState.HEALTHY,
                [str(item.id) for item in linked_outcomes],
                ConfidenceLevel.HIGH,
                "Outcome records are linked.",
            )
            if linked_outcomes or initiative.product_outcomes or initiative.business_outcomes
            else (
                HealthState.AT_RISK,
                [],
                ConfidenceLevel.HIGH,
                "No outcome is documented for the initiative.",
            ),
            "strategic_alignment": (
                HealthState.HEALTHY,
                initiative.objective_ids,
                ConfidenceLevel.HIGH,
                "Objectives are linked.",
            )
            if initiative.objective_ids
            else (
                HealthState.UNKNOWN,
                [],
                ConfidenceLevel.UNKNOWN,
                "Strategic alignment is not documented.",
            ),
            "decision_quality": (
                HealthState.WATCH,
                initiative.decision_ids,
                ConfidenceLevel.MEDIUM,
                "Decision records exist; process quality requires review.",
            )
            if initiative.decision_ids
            else (
                HealthState.UNKNOWN,
                [],
                ConfidenceLevel.UNKNOWN,
                "No decision records are linked.",
            ),
            "execution_progress": (
                HealthState.UNKNOWN,
                initiative.jira_issue_ids,
                ConfidenceLevel.UNKNOWN,
                "Activity records do not establish product progress or outcomes.",
            ),
            "dependency_health": (
                HealthState.AT_RISK,
                [str(item.id) for item in risky_commitments],
                ConfidenceLevel.HIGH,
                "A linked commitment is at risk or missed; review context before attribution.",
            )
            if risky_commitments
            else (
                HealthState.WATCH,
                initiative.dependency_ids,
                ConfidenceLevel.MEDIUM,
                "Dependencies require active review.",
            )
            if initiative.dependency_ids
            else (
                HealthState.HEALTHY,
                [],
                ConfidenceLevel.MEDIUM,
                "No dependencies are documented.",
            ),
            "measurement_readiness": (
                HealthState.HEALTHY,
                [str(item.id) for item in linked_outcomes if item.metric and item.target],
                ConfidenceLevel.HIGH,
                "Metrics and targets are documented.",
            )
            if any(item.metric and item.target for item in linked_outcomes)
            else (
                HealthState.AT_RISK,
                [],
                ConfidenceLevel.HIGH,
                "No linked outcome has both a metric and target.",
            ),
            "learning_velocity": (
                HealthState.WATCH,
                initiative.artifact_ids,
                ConfidenceLevel.MEDIUM,
                "Learning artifacts are linked but require qualitative review.",
            )
            if initiative.artifact_ids
            else (
                HealthState.UNKNOWN,
                [],
                ConfidenceLevel.UNKNOWN,
                "No learning evidence is linked.",
            ),
        }
        return [
            InitiativeHealthDimension(
                dimension=name,
                state=values[name][0],
                evidence_ids=values[name][1],
                confidence=values[name][2],
                explanation=values[name][3],
            )
            for name in HEALTH_DIMENSIONS
        ]

    @staticmethod
    def _signals(
        initiatives: list[Initiative],
        outcomes: list[Outcome],
        commitments: list[Commitment],
        tenant_id: UUID,
        user_id: UUID,
    ) -> list[ManagementSignal]:
        now = datetime.now(UTC)
        signals: list[ManagementSignal] = []
        for initiative in initiatives:
            outcome_records = [item for item in outcomes if initiative.id in item.initiative_ids]
            if (
                not outcome_records
                and not initiative.product_outcomes
                and not initiative.business_outcomes
            ):
                signals.append(
                    ManagementSignal(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        signal_type=SignalType.OUTCOME_GAP,
                        subject_type="initiative",
                        subject_id=str(initiative.id),
                        epistemic_level=EpistemicLevel.DERIVED_SIGNAL,
                        observation=(
                            f"No outcome record is linked to initiative '{initiative.name}'."
                        ),
                        derived_signal=(
                            "Outcome clarity and measurement readiness require attention."
                        ),
                        recommendation=(
                            "Define an outcome, metric, baseline, target, and evidence owner."
                        ),
                        evidence_ids=[f"initiative:{initiative.id}"],
                        confidence=ConfidenceLevel.HIGH,
                        significance=Significance.HIGH,
                        time_window_start=initiative.created_at,
                        time_window_end=now,
                        limitations=[
                            "Missing documentation does not prove that no outcome "
                            "thinking occurred."
                        ],
                    )
                )
            achieved = [
                item
                for item in outcome_records
                if item.status == OutcomeStatus.ACHIEVED and item.evidence_ids
            ]
            if achieved:
                signals.append(
                    ManagementSignal(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        signal_type=SignalType.STRENGTH,
                        subject_type="initiative",
                        subject_id=str(initiative.id),
                        epistemic_level=EpistemicLevel.OBSERVATION,
                        observation=(
                            f"Initiative '{initiative.name}' has an achieved outcome "
                            "with linked evidence."
                        ),
                        recommendation=(
                            "Recognize the documented outcome and review attribution limits."
                        ),
                        evidence_ids=[
                            evidence for item in achieved for evidence in item.evidence_ids
                        ],
                        confidence=ConfidenceLevel.HIGH,
                        significance=Significance.MEDIUM,
                        time_window_start=initiative.created_at,
                        time_window_end=now,
                        limitations=[
                            "Outcome status does not by itself establish causal attribution."
                        ],
                    )
                )
        for commitment in commitments:
            if commitment.status in {CommitmentStatus.AT_RISK, CommitmentStatus.MISSED}:
                signals.append(
                    ManagementSignal(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        signal_type=SignalType.EXECUTION_RISK,
                        subject_type="initiative" if commitment.initiative_id else "commitment",
                        subject_id=str(commitment.initiative_id or commitment.id),
                        epistemic_level=EpistemicLevel.OBSERVATION,
                        observation=(
                            f"Commitment '{commitment.description}' is {commitment.status}."
                        ),
                        derived_signal="A documented commitment needs review.",
                        recommendation=(
                            "Review scope, dependencies, due date changes, and the recorded "
                            "reason before interpreting cause."
                        ),
                        evidence_ids=[*commitment.evidence_ids, f"commitment:{commitment.id}"],
                        confidence=ConfidenceLevel.HIGH,
                        significance=Significance.HIGH
                        if commitment.status == CommitmentStatus.MISSED
                        else Significance.MEDIUM,
                        time_window_start=commitment.created_at,
                        time_window_end=now,
                        limitations=[
                            "Commitment state is not equivalent to product or PM performance."
                        ],
                    )
                )
        owner_gaps: dict[str, list[Initiative]] = defaultdict(list)
        for initiative in initiatives:
            if (
                not initiative.product_outcomes
                and not initiative.business_outcomes
                and not any(initiative.id in outcome.initiative_ids for outcome in outcomes)
            ):
                for owner in initiative.owner_ids:
                    owner_gaps[owner].append(initiative)
        for owner, gaps in owner_gaps.items():
            if len(gaps) >= 3:
                signals.append(
                    ManagementSignal(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        signal_type=SignalType.COACHING_OPPORTUNITY,
                        subject_type="pm",
                        subject_id=owner,
                        epistemic_level=EpistemicLevel.INTERPRETATION,
                        observation=(
                            f"Three or more initiatives owned by {owner} have no linked "
                            f"outcome records: {', '.join(item.name for item in gaps)}."
                        ),
                        interpretation=(
                            "Outcome definition may be a recurring coaching topic; "
                            "manager context is required."
                        ),
                        recommendation=(
                            "Ask how outcomes are defined and where measurement evidence "
                            "is documented."
                        ),
                        evidence_ids=[f"initiative:{item.id}" for item in gaps],
                        confidence=ConfidenceLevel.MEDIUM,
                        significance=Significance.MEDIUM,
                        time_window_start=min(item.created_at for item in gaps),
                        time_window_end=now,
                        limitations=[
                            "This is a documentation pattern, not a conclusion about skill, "
                            "motivation, or performance."
                        ],
                    )
                )
        return signals

    async def _brief_artifact(
        self,
        workflow: WorkflowName,
        title: str,
        data: dict[str, Any],
        tenant_id: UUID,
        user_id: UUID,
    ) -> Artifact:
        state = AgentState(
            user_id=user_id,
            tenant_id=tenant_id,
            request=title,
            status=RunStatus.RUNNING,
            mode="management",
        )
        await self._runs.start(
            state,
            f"{workflow}.v1",
            "deterministic-management",
            self._settings.runtime_version,
            self._settings.constitution_version,
            self._settings.memory_policy_version,
            self._settings.retrieval_policy_version,
            self._settings.tool_contract_version,
            self._settings.mcp_adapter_version,
            "1.0.0",
            {"management": "deterministic.v1"},
        )
        await self._trace(state.run_id, TraceEventType.RUN_STARTED, mode="management")
        await self._trace(
            state.run_id, TraceEventType.WORKFLOW_SELECTED, workflow=workflow, version="1.0.0"
        )
        rendered = self._render(title, data)
        artifact = Artifact(
            tenant_id=tenant_id,
            user_id=user_id,
            artifact_type=ArtifactType.MANAGEMENT_BRIEF,
            title=title,
            structured_data=data,
            rendered_content=rendered,
            workflow_id=state.session_id,
            workflow_name=workflow,
            workflow_version="1.0.0",
            agent_run_id=state.run_id,
            source_ids=self._source_ids(data),
            model_metadata={"generator": "deterministic-management"},
        )
        await self._artifacts.create(artifact)
        await self._trace(
            state.run_id,
            TraceEventType.ARTIFACT_CREATED,
            artifact_id=str(artifact.id),
            artifact_type=artifact.artifact_type,
        )
        state.status = RunStatus.COMPLETED
        state.response = rendered
        await self._trace(state.run_id, TraceEventType.RUN_COMPLETED, status=state.status)
        await self._runs.complete(state)
        return artifact

    @staticmethod
    def _render(title: str, data: dict[str, Any]) -> str:
        lines = [f"# {title}", "", "Status: Draft · Evidence-backed management brief", ""]
        for key, value in data.items():
            lines.extend([f"## {key.replace('_', ' ').title()}", ""])
            if isinstance(value, list):
                lines.extend([f"- {item}" for item in value] or ["- No documented evidence found."])
            else:
                lines.append(str(value))
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _source_ids(data: dict[str, Any]) -> list[str]:
        text = str(data)
        return sorted(
            set(
                part
                for part in text.replace("'", " ").split()
                if part.startswith(("initiative:", "outcome:", "commitment:"))
            )
        )

    @staticmethod
    def _decision_summary(decision: Decision) -> dict[str, Any]:
        return {
            "id": str(decision.id),
            "title": decision.title,
            "status": decision.status,
            "review_at": decision.review_at.isoformat() if decision.review_at else None,
        }

    @staticmethod
    def _questions(profile: PMIntelligenceProfile) -> list[str]:
        questions = []
        if not profile.outcomes:
            questions.append(
                "What outcomes are these initiatives intended to change, and where are "
                "they measured?"
            )
        if profile.risks:
            questions.append("What context or constraints are missing from the documented risks?")
        if profile.coaching_opportunities:
            questions.append(
                "Does this documented pattern reflect a real craft gap, or a "
                "documentation/process gap?"
            )
        questions.append("What recent learning should change our plan or assumptions?")
        return questions

    @staticmethod
    def _profile_evidence_ids(profile: PMIntelligenceProfile) -> list[str]:
        return sorted(
            {f"initiative:{item.id}" for item in profile.initiatives}
            | {f"outcome:{item.id}" for item in profile.outcomes}
            | {
                evidence
                for signal in [
                    *profile.observed_strengths,
                    *profile.coaching_opportunities,
                    *profile.risks,
                ]
                for evidence in signal.evidence_ids
            }
        )

    @staticmethod
    def _launch_collisions(initiatives: list[Initiative]) -> list[str]:
        dated = [item for item in initiatives if item.target_date]
        collisions = []
        for index, first in enumerate(dated):
            for second in dated[index + 1 :]:
                if abs((first.target_date - second.target_date).days) <= 7:
                    collisions.append(
                        f"{first.name} and {second.name} target the same seven-day window."
                    )
        return collisions

    async def _trace(self, run_id: UUID, event_type: TraceEventType, **attributes: Any) -> None:
        await self._traces.append(
            TraceEvent(run_id=run_id, event_type=event_type, attributes=attributes)
        )
