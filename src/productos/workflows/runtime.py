import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from productos.application.ports import TraceRepository
from productos.application.repositories import (
    AgentRunRepository,
    ArtifactRepository,
    WorkingSessionRepository,
)
from productos.atlassian.service import OrganizationService
from productos.config import Settings
from productos.domain.agent import AgentState, RunStatus
from productos.domain.knowledge import (
    EvidenceAvailability,
    EvidenceItem,
    EvidencePacket,
    KnowledgeSearchRequest,
)
from productos.domain.tools import PermissionContext
from productos.domain.trace import TraceEvent, TraceEventType
from productos.domain.workflow import (
    Artifact,
    ArtifactType,
    Assumption,
    EvidenceLedger,
    ExperimentDesign,
    ResearchCoverage,
    ResearchQuestion,
    ReviewFinding,
    ReviewSeverity,
    StrategyOption,
    WorkflowDefinition,
    WorkflowExecuteRequest,
    WorkflowExecution,
    WorkflowName,
    WorkflowResult,
    WorkflowStage,
    WorkflowStageState,
)
from productos.retrieval.service import HybridRetrievalService


def _definition(
    name: WorkflowName,
    stages: list[str],
    artifact_type: ArtifactType,
    profile: str,
    required: list[str] | None = None,
) -> WorkflowDefinition:
    return WorkflowDefinition(
        name=name,
        version="1.0.0",
        supported_intents=[name.value],
        required_capabilities=required or ["knowledge.search"],
        optional_capabilities=["organization.search", "memory.search"],
        stages=[WorkflowStage(name=item) for item in stages],
        artifact_type=artifact_type,
        evaluation_profile=profile,
        max_iterations=3,
    )


def workflow_definitions() -> dict[WorkflowName, WorkflowDefinition]:
    return {
        WorkflowName.DEEP_RESEARCH: _definition(
            WorkflowName.DEEP_RESEARCH,
            [
                "frame_question",
                "decompose_questions",
                "retrieve_internal_evidence",
                "retrieve_organizational_evidence",
                "evaluate_evidence",
                "detect_contradictions",
                "identify_unknowns",
                "synthesize",
                "generate_options",
                "recommend",
                "create_artifact",
            ],
            ArtifactType.RESEARCH_REPORT,
            "research.v1",
        ),
        WorkflowName.PRODUCT_STRATEGY: _definition(
            WorkflowName.PRODUCT_STRATEGY,
            [
                "frame_problem",
                "define_desired_outcome",
                "retrieve_context",
                "identify_assumptions",
                "identify_constraints",
                "generate_options",
                "evaluate_options",
                "analyze_tradeoffs",
                "recommend",
                "define_validation_plan",
                "create_artifact",
            ],
            ArtifactType.STRATEGY_MEMO,
            "strategy.v1",
        ),
        WorkflowName.PRODUCT_REVIEW: _definition(
            WorkflowName.PRODUCT_REVIEW,
            ["parse_document", "apply_rubric", "calibrate_severity", "create_artifact"],
            ArtifactType.PRODUCT_REVIEW,
            "product_review.v1",
            ["document.read"],
        ),
        WorkflowName.SPEC_EXECUTION: _definition(
            WorkflowName.SPEC_EXECUTION,
            [
                "retrieve_spec",
                "extract_requirements",
                "retrieve_jira",
                "map_coverage",
                "create_artifact",
            ],
            ArtifactType.SPEC_EXECUTION_REVIEW,
            "spec_execution.v1",
            ["confluence.page.read", "jira.search"],
        ),
        WorkflowName.EXPERIMENT_DESIGN: _definition(
            WorkflowName.EXPERIMENT_DESIGN,
            [
                "frame_problem",
                "state_hypothesis",
                "design_comparison",
                "define_measurement",
                "identify_risks",
                "create_artifact",
            ],
            ArtifactType.EXPERIMENT_PLAN,
            "experiment.v1",
        ),
        WorkflowName.DECISION_MEMO: _definition(
            WorkflowName.DECISION_MEMO,
            [
                "frame_problem",
                "retrieve_evidence",
                "generate_options",
                "record_tradeoffs",
                "define_validation",
                "create_artifact",
            ],
            ArtifactType.DECISION_MEMO,
            "decision.v1",
        ),
    }


class WorkflowRuntime:
    """One deterministic, inspectable runtime for all Milestone 4 workflows."""

    def __init__(
        self,
        artifacts: ArtifactRepository,
        traces: TraceRepository,
        settings: Settings,
        runs: AgentRunRepository,
        retrieval: HybridRetrievalService,
        organization: OrganizationService | None = None,
        work: WorkingSessionRepository | None = None,
    ) -> None:
        self._definitions = workflow_definitions()
        self._artifacts = artifacts
        self._traces = traces
        self._settings = settings
        self._runs = runs
        self._retrieval = retrieval
        self._organization = organization
        self._work = work

    def definitions(self) -> list[WorkflowDefinition]:
        return list(self._definitions.values())

    async def execute(
        self, request: WorkflowExecuteRequest, tenant_id: UUID, user_id: UUID
    ) -> WorkflowResult:
        request = request.model_copy(update={"tenant_id": tenant_id, "user_id": user_id})
        definition = self._definitions[request.workflow]
        state = AgentState(
            user_id=user_id,
            tenant_id=tenant_id,
            working_session_id=request.working_session_id,
            request=request.objective,
            status=RunStatus.RUNNING,
            mode="workflow",
            plan={"stages": [stage.name for stage in definition.stages]},
        )
        execution = WorkflowExecution(
            run_id=state.run_id,
            definition_name=definition.name,
            definition_version=definition.version,
        )
        await self._runs.start(
            state,
            f"{definition.name}.v1",
            "deterministic-workflow",
            self._settings.runtime_version,
            self._settings.constitution_version,
            self._settings.memory_policy_version,
            self._settings.retrieval_policy_version,
            self._settings.tool_contract_version,
            self._settings.mcp_adapter_version,
            definition.version,
            {"workflow": "deterministic.v1"},
        )
        await self._trace(state.run_id, TraceEventType.RUN_STARTED, mode="workflow")
        await self._trace(
            state.run_id,
            TraceEventType.WORKFLOW_SELECTED,
            workflow=definition.name,
            version=definition.version,
        )
        await self._trace(
            state.run_id,
            TraceEventType.PLAN_CREATED,
            stages=[stage.name for stage in definition.stages],
            max_iterations=definition.max_iterations,
        )
        try:
            packet = await self._evidence(request, tenant_id, user_id, state.run_id)
            ledger = self._ledger(request.objective, packet)
            structured = await self._build(request, definition, ledger, state.run_id, execution)
            title = request.title or self._title(definition.name, request.objective)
            rendered = self._render(title, definition.name, structured, ledger)
            artifact = Artifact(
                tenant_id=tenant_id,
                user_id=user_id,
                artifact_type=definition.artifact_type,
                title=title,
                structured_data=structured,
                rendered_content=rendered,
                workflow_id=execution.id,
                workflow_name=definition.name,
                workflow_version=definition.version,
                agent_run_id=state.run_id,
                working_session_id=request.working_session_id,
                source_ids=[f"{item.source_type}:{item.source_id}" for item in self._all(ledger)],
                model_metadata={"generator": "deterministic-workflow", "prompt_version": "none"},
            )
            await self._artifacts.create(artifact)
            if self._work and request.working_session_id:
                await self._work.attach_artifact(
                    request.working_session_id,
                    user_id,
                    artifact.id,
                    [
                        str(item.knowledge_item_id)
                        for item in self._all(ledger)
                        if item.knowledge_item_id
                    ],
                )
            await self._trace(
                state.run_id,
                TraceEventType.ARTIFACT_CREATED,
                artifact_id=str(artifact.id),
                artifact_type=artifact.artifact_type,
                status=artifact.status,
            )
            execution.status = "completed"
            execution.completed_at = datetime.now(UTC)
            state.status = RunStatus.COMPLETED
            state.response = rendered
            state.retrieved_context = [
                {
                    "evidence_id": item.id,
                    "source_type": item.source_type,
                    "source_id": item.source_id,
                }
                for item in self._all(ledger)
            ]
            await self._trace(state.run_id, TraceEventType.RUN_COMPLETED, status=state.status)
            await self._runs.complete(state)
            return WorkflowResult(execution=execution, artifact=artifact, evidence_ledger=ledger)
        except Exception as exc:
            state.status = RunStatus.FAILED
            execution.status = "failed"
            execution.completed_at = datetime.now(UTC)
            await self._trace(
                state.run_id, TraceEventType.RUN_FAILED, error_type=type(exc).__name__
            )
            await self._runs.complete(state, type(exc).__name__)
            raise

    async def _evidence(
        self, request: WorkflowExecuteRequest, tenant_id: UUID, user_id: UUID, run_id: UUID
    ) -> EvidencePacket:
        await self._trace(run_id, TraceEventType.RETRIEVAL_STARTED, workflow=request.workflow)
        if (
            request.workflow != WorkflowName.SPEC_EXECUTION
            and request.workspace_id
            and self._organization
        ):
            packet = await self._organization.search(
                run_id,
                request.objective,
                PermissionContext(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    workspace_id=request.workspace_id,
                    permissions=(
                        {"atlassian:read"} if self._settings.atlassian_read_enabled else set()
                    ),
                ),
                request.workspace_id,
            )
        else:
            packet = await self._retrieval.search(
                KnowledgeSearchRequest(query=request.objective, limit=12), tenant_id, user_id
            )
        if request.source_text:
            source = EvidenceItem(
                id="U1",
                topic=request.objective,
                content=request.source_text,
                source_type="user_document",
                source_id=f"workflow-input:{run_id}",
                title=request.title or "User-provided document",
                authority=0.7,
                relevance=1.0,
                freshness=1.0,
                confidence=1.0,
            )
            packet.evidence.insert(0, source)
            packet.availability = EvidenceAvailability.EVIDENCE_FOUND
            packet.source_coverage["user_document"] = 1
        await self._trace(
            run_id,
            TraceEventType.RETRIEVAL_COMPLETED,
            availability=packet.availability,
            evidence_count=len(packet.evidence),
        )
        await self._trace(
            run_id,
            TraceEventType.EVIDENCE_PACKET_CREATED,
            evidence_ids=[item.id for item in packet.evidence],
            known_unknowns=packet.known_unknowns,
        )
        return packet

    @staticmethod
    def _ledger(topic: str, packet: EvidencePacket) -> EvidenceLedger:
        contradiction_ids = {value for item in packet.contradictions for value in item.evidence_ids}
        unique: dict[tuple[str, str, str], EvidenceItem] = {}
        for item in packet.evidence:
            unique.setdefault((item.source_type, item.source_id, item.content), item)
        contradicting = [item for item in unique.values() if item.id in contradiction_ids]
        supporting = [item for item in unique.values() if item.id not in contradiction_ids]
        confidence = "high" if len(supporting) >= 3 else "medium" if supporting else "unknown"
        unknowns = list(packet.known_unknowns)
        if not unique:
            unknowns.append("No accessible evidence was found; conclusions remain unknown.")
        return EvidenceLedger(
            topic=topic,
            supporting=supporting,
            contradicting=contradicting,
            unknowns=list(dict.fromkeys(unknowns)),
            confidence=confidence,
        )

    async def _build(
        self,
        request: WorkflowExecuteRequest,
        definition: WorkflowDefinition,
        ledger: EvidenceLedger,
        run_id: UUID,
        execution: WorkflowExecution,
    ) -> dict[str, Any]:
        builders: dict[WorkflowName, Callable[[], Awaitable[dict[str, Any]] | dict[str, Any]]] = {
            WorkflowName.DEEP_RESEARCH: lambda: self._research(request, ledger),
            WorkflowName.PRODUCT_STRATEGY: lambda: self._strategy(request, ledger),
            WorkflowName.PRODUCT_REVIEW: lambda: self._review(request, ledger),
            WorkflowName.SPEC_EXECUTION: lambda: self._spec_execution(request, ledger, run_id),
            WorkflowName.EXPERIMENT_DESIGN: lambda: self._experiment(request, ledger),
            WorkflowName.DECISION_MEMO: lambda: self._decision(request, ledger),
        }
        result: dict[str, Any] | None = None
        for stage in definition.stages:
            await self._trace(run_id, TraceEventType.WORKFLOW_STAGE_STARTED, stage=stage.name)
            if stage.name == "create_artifact":
                built = builders[definition.name]()
                result = await built if hasattr(built, "__await__") else built
            execution.stages.append(
                WorkflowStageState(name=stage.name, status="completed", summary="Stage completed.")
            )
            await self._trace(run_id, TraceEventType.WORKFLOW_STAGE_COMPLETED, stage=stage.name)
        return result or {}

    @staticmethod
    def _research(request: WorkflowExecuteRequest, ledger: EvidenceLedger) -> dict[str, Any]:
        topic = request.objective.rstrip(" ?")
        questions = [
            ResearchQuestion(
                question=f"What customer problem underlies {topic}?",
                importance="critical",
                required_sources=["customer_evidence"],
                status="answered" if ledger.supporting else "unanswered",
                evidence_ids=[item.id for item in ledger.supporting],
                answer=(ledger.supporting[0].content[:500] if ledger.supporting else None),
                confidence=ledger.confidence,
            ),
            ResearchQuestion(
                question="What internal capability and constraints are documented?",
                importance="high",
                required_sources=["internal"],
                status="answered" if ledger.supporting else "unanswered",
                evidence_ids=[item.id for item in ledger.supporting],
                confidence=ledger.confidence,
            ),
            ResearchQuestion(
                question="What outcome and measurement evidence exists?",
                importance="critical",
                required_sources=["metric"],
                status="unanswered",
                confidence="unknown",
            ),
        ]
        coverage_terms = {
            "customer_problem": {"customer", "user", "problem", "pain"},
            "customer_evidence": {"interview", "research", "feedback", "ticket"},
            "internal_capability": {"system", "platform", "architecture", "capability"},
            "organizational_history": {"decision", "history", "previous", "approved"},
            "competitive_context": {"competitor", "market", "alternative"},
            "technical_feasibility": {"technical", "engineering", "latency", "dependency"},
            "business_impact": {"revenue", "cost", "business", "conversion"},
            "measurement": {"metric", "measure", "baseline", "target"},
        }
        text = " ".join(item.content.casefold() for item in ledger.supporting)
        coverage = [
            ResearchCoverage(
                dimension=name,
                status="evidence_found"
                if terms & set(re.findall(r"[a-z0-9]+", text))
                else "no_evidence_found",
                evidence_ids=[item.id for item in ledger.supporting]
                if any(term in text for term in terms)
                else [],
                limitation=None
                if any(term in text for term in terms)
                else "No documented evidence found in accessible sources.",
            )
            for name, terms in coverage_terms.items()
        ]
        return {
            "question": request.objective,
            "research_questions": [item.model_dump(mode="json") for item in questions],
            "coverage": [item.model_dump(mode="json") for item in coverage],
            "synthesis": (
                "Accessible evidence is summarized below."
                if ledger.supporting
                else "Evidence is insufficient for a material conclusion."
            ),
            "recommendation": (
                "Use the evidence to frame options, while validating uncovered critical dimensions."
                if ledger.supporting
                else (
                    "Collect customer, outcome, and feasibility evidence before recommending "
                    "an investment."
                )
            ),
            "confidence": ledger.confidence,
            "unknowns": ledger.unknowns,
        }

    @staticmethod
    def _strategy(request: WorkflowExecuteRequest, ledger: EvidenceLedger) -> dict[str, Any]:
        evidence_ids = [item.id for item in ledger.supporting]
        assumptions = [
            Assumption(
                statement="The documented problem represents a material user need.",
                category="customer",
                confidence="medium" if evidence_ids else "low",
                criticality="critical",
                evidence_ids=evidence_ids,
                validation_status="partially_validated" if evidence_ids else "unvalidated",
            ),
            Assumption(
                statement="A measurable outcome can be instrumented.",
                category="business",
                confidence="low",
                criticality="critical",
            ),
        ]
        options = [
            StrategyOption(
                name="Do not invest yet",
                description="Preserve capacity while closing evidence gaps.",
                advantages=["Avoids premature commitment"],
                tradeoffs=["Delays potential value"],
                reversibility="two_way_door",
            ),
            StrategyOption(
                name="Run a bounded validation",
                description="Test the critical assumptions with a narrow experiment.",
                advantages=["Creates learning before scale"],
                tradeoffs=["Requires instrumentation and a decision rule"],
                reversibility="two_way_door",
                evidence_ids=evidence_ids,
            ),
            StrategyOption(
                name="Commit to full delivery",
                description="Fund the complete solution now.",
                advantages=["Fastest path if assumptions hold"],
                tradeoffs=["Highest exposure to unvalidated assumptions"],
                reversibility="one_way_door",
                evidence_ids=evidence_ids,
            ),
        ]
        recommendation = (
            "Run a bounded validation before full commitment."
            if evidence_ids
            else "Do not commit until critical customer and measurement evidence is collected."
        )
        return {
            "problem": request.objective,
            "desired_outcome": request.context.get(
                "desired_outcome",
                "Not specified; define a measurable customer or business outcome.",
            ),
            "evidence_ids": evidence_ids,
            "assumptions": [item.model_dump(mode="json") for item in assumptions],
            "constraints": request.context.get("constraints", []),
            "options": [item.model_dump(mode="json") for item in options],
            "recommendation": recommendation,
            "what_could_make_this_wrong": [
                "New customer evidence may change problem priority.",
                "Technical feasibility and operational burden remain insufficiently evidenced.",
            ],
            "validation_plan": (
                "Define a primary outcome, baseline, guardrails, and a time-bounded decision rule."
            ),
            "confidence": ledger.confidence,
        }

    @staticmethod
    def _review(request: WorkflowExecuteRequest, ledger: EvidenceLedger) -> dict[str, Any]:
        text = request.source_text or ""
        lowered = text.casefold()
        rubric = [
            ("problem clarity", ["problem", "why"]),
            ("customer evidence", ["customer", "research", "evidence"]),
            ("target user", ["target user", "persona", "user"]),
            ("desired outcome", ["outcome", "goal"]),
            ("non-goals", ["non-goal", "out of scope"]),
            ("requirements", ["requirement", "must"]),
            ("edge cases", ["edge case", "failure"]),
            ("dependencies", ["dependency", "depends"]),
            ("success metrics", ["success metric", "kpi", "metric"]),
            ("instrumentation", ["instrumentation", "tracking", "event"]),
            ("rollout", ["rollout", "launch"]),
            ("open questions", ["open question", "tbd"]),
        ]
        if any(term in lowered for term in ("ai", "model", "agent", "prompt")):
            rubric.extend(
                [
                    ("hallucination risk", ["hallucination", "grounding"]),
                    ("fallback behavior", ["fallback", "human handoff"]),
                    ("observability", ["trace", "observability"]),
                    ("evaluation", ["eval", "accuracy"]),
                    ("prompt injection", ["prompt injection", "untrusted"]),
                    ("cost", ["cost", "token"]),
                ]
            )
        findings = []
        for item, terms in rubric:
            if not any(term in lowered for term in terms):
                severity = (
                    ReviewSeverity.MAJOR
                    if item
                    in {"problem clarity", "customer evidence", "success metrics", "requirements"}
                    else ReviewSeverity.QUESTION
                )
                findings.append(
                    ReviewFinding(
                        rubric_item=item,
                        severity=severity,
                        observation=f"The document does not contain identifiable {item} evidence.",
                        recommendation=(
                            f"Add an explicit {item} section or mark it as an open question."
                        ),
                    )
                )
        return {
            "document_title": request.title or "Product document",
            "findings": [item.model_dump(mode="json") for item in findings],
            "strengths": [item for item, terms in rubric if any(term in lowered for term in terms)],
            "evidence_ids": [item.id for item in ledger.supporting],
            "limitations": [
                "This review checks documented coverage; it does not prove product quality "
                "or implementation."
            ],
        }

    async def _spec_execution(
        self, request: WorkflowExecuteRequest, ledger: EvidenceLedger, run_id: UUID
    ) -> dict[str, Any]:
        if not self._organization:
            return {
                "status": "evidence_inaccessible",
                "unknowns": ["Organizational retrieval is unavailable."],
            }
        result = await self._organization.compare_spec_execution(
            run_id,
            request.page_id or "",
            PermissionContext(
                tenant_id=request.tenant_id or UUID(int=0),
                user_id=request.user_id or UUID(int=0),
                workspace_id=request.workspace_id,
                permissions={"atlassian:read"} if self._settings.atlassian_read_enabled else set(),
            ),
            request.workspace_id,
            request.projects,
        )
        return result.model_dump(mode="json")

    @staticmethod
    def _experiment(request: WorkflowExecuteRequest, ledger: EvidenceLedger) -> dict[str, Any]:
        context = request.context
        design = ExperimentDesign(
            problem=request.objective,
            hypothesis=str(
                context.get(
                    "hypothesis",
                    "If the proposed mechanism addresses the documented problem, the primary "
                    "outcome will improve.",
                )
            ),
            mechanism=str(context.get("mechanism", "Proposed product change")),
            target_population=str(context.get("target_population", "Not specified")),
            treatment=str(context.get("treatment", "Users receive the proposed experience")),
            control=str(context.get("control", "Users retain the current experience")),
            primary_metric=str(
                context.get("primary_metric", "Not specified; define before launch")
            ),
            secondary_metrics=list(context.get("secondary_metrics", [])),
            guardrails=list(context.get("guardrails", ["quality", "latency", "support burden"])),
            segmentation=list(context.get("segmentation", [])),
            instrumentation=list(
                context.get("instrumentation", ["exposure event", "primary outcome event"])
            ),
            risks=["Selection bias", "Novelty effects", "Insufficient exposure", *ledger.unknowns],
            decision_rule=str(
                context.get(
                    "decision_rule",
                    "Define an effect threshold, guardrail limits, and minimum evidence window "
                    "before starting.",
                )
            ),
            expected_learning=str(
                context.get(
                    "expected_learning",
                    "Whether the proposed mechanism changes the primary outcome without "
                    "unacceptable guardrail harm.",
                )
            ),
            agent_configuration={
                key: context.get(key)
                for key in (
                    "model_version",
                    "prompt_version",
                    "tool_set",
                    "memory_version",
                    "language",
                    "traffic_segment",
                )
            },
        )
        return design.model_dump(mode="json") | {
            "evidence_ids": [item.id for item in ledger.supporting]
        }

    @staticmethod
    def _decision(request: WorkflowExecuteRequest, ledger: EvidenceLedger) -> dict[str, Any]:
        context = request.context
        return {
            "problem": request.objective,
            "context": context.get("background", "No additional context supplied."),
            "evidence": [item.id for item in ledger.supporting],
            "options": context.get("options", ["Defer", "Run a bounded validation", "Commit now"]),
            "decision": context.get(
                "proposed_decision", "No decision selected; this artifact remains a draft."
            ),
            "rationale": context.get(
                "rationale", "Rationale requires user review and explicit selection."
            ),
            "tradeoffs": context.get("tradeoffs", []),
            "risks": ["Evidence gaps may change the preferred option.", *ledger.unknowns],
            "assumptions": context.get("assumptions", []),
            "validation_plan": context.get(
                "validation_plan", "Define outcome evidence and a review trigger."
            ),
            "review_trigger": context.get(
                "review_trigger",
                "Review when material contradictory evidence or outcome data emerges.",
            ),
            "memory_promotion": "requires_explicit_approval",
        }

    @staticmethod
    def _render(
        title: str, workflow: WorkflowName, data: dict[str, Any], ledger: EvidenceLedger
    ) -> str:
        lines = [f"# {title}", "", f"Status: Draft · Workflow: {workflow.value} v1.0.0", ""]
        for key, value in data.items():
            lines.extend(
                [f"## {key.replace('_', ' ').title()}", "", WorkflowRuntime._markdown(value), ""]
            )
        lines.extend(["## Evidence ledger", "", f"Confidence: {ledger.confidence}"])
        if ledger.supporting:
            lines.extend(["", "### Supporting evidence"])
            lines.extend(
                [f"- [{item.id}] {item.title} — {item.content[:240]}" for item in ledger.supporting]
            )
        if ledger.contradicting:
            lines.extend(["", "### Contradicting evidence"])
            lines.extend(
                [
                    f"- [{item.id}] {item.title} — {item.content[:240]}"
                    for item in ledger.contradicting
                ]
            )
        if ledger.unknowns:
            lines.extend(["", "### Known unknowns", *[f"- {item}" for item in ledger.unknowns]])
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _markdown(value: Any) -> str:
        if isinstance(value, list):
            return (
                "\n".join(f"- {WorkflowRuntime._markdown(item)}" for item in value)
                or "- None documented"
            )
        if isinstance(value, dict):
            return (
                "\n".join(
                    f"- **{key.replace('_', ' ').title()}:** {WorkflowRuntime._markdown(item)}"
                    for key, item in value.items()
                )
                or "No documented data."
            )
        if value is None or value == "":
            return "Unknown / not documented."
        return str(value)

    @staticmethod
    def _title(workflow: WorkflowName, objective: str) -> str:
        prefix = workflow.value.replace("_", " ").title()
        return f"{prefix}: {objective.strip()[:100]}"

    @staticmethod
    def _all(ledger: EvidenceLedger) -> list[EvidenceItem]:
        return [*ledger.supporting, *ledger.contradicting, *ledger.neutral]

    async def _trace(self, run_id: UUID, event_type: TraceEventType, **attributes: Any) -> None:
        await self._traces.append(
            TraceEvent(run_id=run_id, event_type=event_type, attributes=attributes)
        )
