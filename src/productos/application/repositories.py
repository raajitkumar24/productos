from __future__ import annotations

from typing import Protocol
from uuid import UUID

from productos.domain.agent import AgentState
from productos.domain.conversation import (
    Conversation,
    ConversationDetail,
    Message,
    WorkingSession,
    WorkingSessionStatus,
)
from productos.domain.evaluation import EvaluationCaseResult, EvaluationRun, EvaluationRunDetail
from productos.domain.knowledge import (
    KnowledgeChunk,
    KnowledgeItem,
    KnowledgeItemDetail,
    RetrievalCandidate,
)
from productos.domain.management import (
    AttentionSignal,
    Commitment,
    Initiative,
    ManagementSignal,
    Outcome,
    SignalCorrection,
)
from productos.domain.memory import (
    Belief,
    Decision,
    Memory,
    MemoryRelationship,
    MemoryStatus,
    MemoryType,
)
from productos.domain.proactive import (
    ChangeSnapshot,
    NotificationPreferences,
    ProactiveNotification,
    ProactiveSchedule,
)
from productos.domain.tools import ToolCallRecord
from productos.domain.workflow import Artifact, ArtifactStatus


class AgentRunRepository(Protocol):
    async def start(
        self,
        state: AgentState,
        workflow: str,
        model: str,
        runtime_version: str,
        constitution_version: str,
        memory_policy_version: str,
        retrieval_policy_version: str,
        tool_contract_version: str,
        mcp_adapter_version: str,
        workflow_version: str = "1.0.0",
        prompt_versions: dict[str, str] | None = None,
    ) -> None: ...

    async def complete(self, state: AgentState, error_type: str | None = None) -> None: ...

    async def owns(self, run_id: UUID, tenant_id: UUID, user_id: UUID) -> bool: ...


class EvaluationRepository(Protocol):
    async def create_run(self, run: EvaluationRun) -> EvaluationRun: ...

    async def add_case(self, case: EvaluationCaseResult) -> EvaluationCaseResult: ...

    async def update_run(self, run: EvaluationRun) -> EvaluationRun: ...

    async def get_run(
        self, run_id: UUID, tenant_id: UUID, user_id: UUID
    ) -> EvaluationRunDetail | None: ...

    async def list_runs(self, tenant_id: UUID, user_id: UUID) -> list[EvaluationRun]: ...


class ToolCallRepository(Protocol):
    async def create(self, record: ToolCallRecord) -> None: ...

    async def update(self, record: ToolCallRecord) -> None: ...


class ConversationRepository(Protocol):
    async def create(self, conversation: Conversation) -> Conversation: ...

    async def get(self, conversation_id: UUID, user_id: UUID) -> ConversationDetail | None: ...

    async def add_message(self, message: Message) -> Message: ...


class WorkingSessionRepository(Protocol):
    async def create(self, session: WorkingSession) -> WorkingSession: ...

    async def get(self, session_id: UUID, user_id: UUID) -> WorkingSession | None: ...

    async def list(
        self, user_id: UUID, status: WorkingSessionStatus | None = None
    ) -> list[WorkingSession]: ...

    async def attach_artifact(
        self, session_id: UUID, user_id: UUID, artifact_id: UUID, evidence_ids: list[str]
    ) -> None: ...


class ArtifactRepository(Protocol):
    async def create(self, artifact: Artifact) -> Artifact: ...

    async def get(self, artifact_id: UUID, tenant_id: UUID, user_id: UUID) -> Artifact | None: ...

    async def list(
        self,
        tenant_id: UUID,
        user_id: UUID,
        artifact_type: str | None = None,
        status: ArtifactStatus | None = None,
    ) -> list[Artifact]: ...


class ManagementRepository(Protocol):
    async def create_initiative(self, initiative: Initiative) -> Initiative: ...

    async def update_initiative(self, initiative: Initiative) -> Initiative: ...

    async def get_initiative(
        self, initiative_id: UUID, tenant_id: UUID, user_id: UUID
    ) -> Initiative | None: ...

    async def list_initiatives(self, tenant_id: UUID, user_id: UUID) -> list[Initiative]: ...

    async def create_outcome(self, outcome: Outcome) -> Outcome: ...

    async def list_outcomes(self, tenant_id: UUID, user_id: UUID) -> list[Outcome]: ...

    async def create_commitment(self, commitment: Commitment) -> Commitment: ...

    async def update_commitment(self, commitment: Commitment) -> Commitment: ...

    async def get_commitment(
        self, commitment_id: UUID, tenant_id: UUID, user_id: UUID
    ) -> Commitment | None: ...

    async def list_commitments(self, tenant_id: UUID, user_id: UUID) -> list[Commitment]: ...

    async def replace_signals(
        self, tenant_id: UUID, user_id: UUID, signals: list[ManagementSignal]
    ) -> list[ManagementSignal]: ...

    async def get_signal(
        self, signal_id: UUID, tenant_id: UUID, user_id: UUID
    ) -> ManagementSignal | None: ...

    async def update_signal(self, signal: ManagementSignal) -> ManagementSignal: ...

    async def list_signals(self, tenant_id: UUID, user_id: UUID) -> list[ManagementSignal]: ...

    async def add_correction(self, correction: SignalCorrection) -> SignalCorrection: ...

    async def list_corrections(self, signal_id: UUID, user_id: UUID) -> list[SignalCorrection]: ...

    async def replace_attention(
        self, tenant_id: UUID, user_id: UUID, signals: list[AttentionSignal]
    ) -> list[AttentionSignal]: ...

    async def list_attention(self, tenant_id: UUID, user_id: UUID) -> list[AttentionSignal]: ...


class ProactiveRepository(Protocol):
    async def create_schedule(self, schedule: ProactiveSchedule) -> ProactiveSchedule: ...

    async def update_schedule(self, schedule: ProactiveSchedule) -> ProactiveSchedule: ...

    async def get_schedule(
        self, schedule_id: UUID, tenant_id: UUID, user_id: UUID
    ) -> ProactiveSchedule | None: ...

    async def list_schedules(self, tenant_id: UUID, user_id: UUID) -> list[ProactiveSchedule]: ...

    async def get_preferences(
        self, tenant_id: UUID, user_id: UUID
    ) -> NotificationPreferences | None: ...

    async def save_preferences(
        self, preferences: NotificationPreferences
    ) -> NotificationPreferences: ...

    async def get_snapshot(
        self, tenant_id: UUID, user_id: UUID, subject_type: str, subject_id: str
    ) -> ChangeSnapshot | None: ...

    async def save_snapshot(self, snapshot: ChangeSnapshot) -> ChangeSnapshot: ...

    async def create_notification(
        self, notification: ProactiveNotification
    ) -> ProactiveNotification | None: ...

    async def update_notification(
        self, notification: ProactiveNotification
    ) -> ProactiveNotification: ...

    async def get_notification(
        self, notification_id: UUID, tenant_id: UUID, user_id: UUID
    ) -> ProactiveNotification | None: ...

    async def list_notifications(
        self, tenant_id: UUID, user_id: UUID
    ) -> list[ProactiveNotification]: ...


class MemoryRepository(Protocol):
    async def insert(self, memory: Memory) -> Memory: ...

    async def get(self, memory_id: UUID, user_id: UUID) -> Memory | None: ...

    async def list(
        self,
        user_id: UUID,
        memory_type: MemoryType | None = None,
        status: MemoryStatus | None = None,
        limit: int = 100,
    ) -> list[Memory]: ...

    async def find_duplicate(
        self, user_id: UUID, memory_type: MemoryType, normalized_content: str
    ) -> Memory | None: ...

    async def find_active_by_key(
        self, user_id: UUID, memory_type: MemoryType, memory_key: str
    ) -> Memory | None: ...

    async def update(self, memory: Memory) -> Memory: ...

    async def add_relationship(self, relationship: MemoryRelationship) -> MemoryRelationship: ...

    async def relationships(
        self, memory_id: UUID
    ) -> tuple[list[MemoryRelationship], list[MemoryRelationship]]: ...


class DecisionRepository(Protocol):
    async def create(self, decision: Decision) -> Decision: ...

    async def get(self, decision_id: UUID, user_id: UUID) -> Decision | None: ...

    async def list(self, user_id: UUID) -> list[Decision]: ...

    async def supersede_by_memory(self, memory_id: UUID) -> None: ...


class BeliefRepository(Protocol):
    async def create(self, belief: Belief) -> Belief: ...

    async def get(self, belief_id: UUID, user_id: UUID) -> Belief | None: ...

    async def list(self, user_id: UUID) -> list[Belief]: ...

    async def supersede_by_memory(self, memory_id: UUID) -> None: ...


class KnowledgeRepository(Protocol):
    async def active_source(
        self, tenant_id: UUID, user_id: UUID, source_type: str, source_id: str
    ) -> KnowledgeItem | None: ...

    async def create(
        self,
        item: KnowledgeItem,
        chunks: list[KnowledgeChunk],
        superseded_item_id: UUID | None = None,
    ) -> None: ...

    async def get(
        self, item_id: UUID, tenant_id: UUID, user_id: UUID
    ) -> KnowledgeItemDetail | None: ...

    async def semantic_search(
        self,
        tenant_id: UUID,
        user_id: UUID,
        query_embedding: list[float],
        source_types: list[str],
        projects: list[str],
        updated_after: object | None,
        limit: int,
    ) -> list[RetrievalCandidate]: ...

    async def lexical_search(
        self,
        tenant_id: UUID,
        user_id: UUID,
        query: str,
        keywords: list[str],
        source_types: list[str],
        projects: list[str],
        updated_after: object | None,
        limit: int,
    ) -> list[RetrievalCandidate]: ...
