from __future__ import annotations

import math
import re
from datetime import UTC, datetime, time
from uuid import NAMESPACE_URL, UUID, uuid5

from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from productos.domain.agent import AgentState
from productos.domain.conversation import (
    Conversation,
    ConversationDetail,
    Message,
    MessageRole,
    WorkingSession,
    WorkingSessionStatus,
)
from productos.domain.evaluation import (
    EvaluationCaseResult,
    EvaluationCaseStatus,
    EvaluationJudgment,
    EvaluationRun,
    EvaluationRunDetail,
    EvaluationRunStatus,
)
from productos.domain.knowledge import (
    DocumentFormat,
    KnowledgeChunk,
    KnowledgeItem,
    KnowledgeItemDetail,
    KnowledgeStatus,
    RetrievalCandidate,
    Sensitivity,
)
from productos.domain.management import (
    AttentionSignal,
    AttributionType,
    Commitment,
    CommitmentHistory,
    CommitmentStatus,
    ConfidenceLevel,
    CorrectionAction,
    EpistemicLevel,
    Initiative,
    InitiativeHealthDimension,
    InitiativeStatus,
    ManagementSignal,
    Outcome,
    OutcomeStatus,
    OutcomeType,
    SignalCorrection,
    SignalStatus,
    SignalType,
    Significance,
)
from productos.domain.memory import (
    Belief,
    BeliefStatus,
    Decision,
    DecisionStatus,
    Memory,
    MemoryRelationship,
    MemoryRelationshipType,
    MemoryStatus,
    MemoryType,
    ProvenanceType,
)
from productos.domain.proactive import (
    ChangeSnapshot,
    NotificationPreferences,
    NotificationStatus,
    ProactiveNotification,
    ProactiveSchedule,
    ScheduleFrequency,
    ScheduleKind,
)
from productos.domain.tools import ToolCallRecord
from productos.domain.trace import TraceEvent, TraceEventType
from productos.domain.workflow import Artifact, ArtifactStatus, ArtifactType, WorkflowName
from productos.infrastructure.persistence.models import (
    AgentRunRow,
    ArtifactRow,
    AttentionSignalRow,
    BeliefRow,
    ChangeSnapshotRow,
    CommitmentRow,
    ConversationRow,
    DecisionRow,
    EvaluationCaseRow,
    EvaluationRunRow,
    InitiativeRow,
    KnowledgeChunkRow,
    KnowledgeItemRow,
    ManagementSignalRow,
    MemoryRelationshipRow,
    MemoryRow,
    MessageRow,
    NotificationPreferencesRow,
    OrganizationRow,
    OutcomeRow,
    ProactiveNotificationRow,
    ProactiveScheduleRow,
    SignalCorrectionRow,
    ToolCallRow,
    TraceEventRow,
    UserRow,
    WorkingSessionRow,
)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


async def _ensure_user(session: AsyncSession, user_id: UUID) -> None:
    if await session.get(UserRow, str(user_id)) is None:
        session.add(UserRow(id=str(user_id), created_at=datetime.now(UTC)))
        await session.flush()


async def _ensure_organization(session: AsyncSession, tenant_id: UUID) -> None:
    if await session.get(OrganizationRow, str(tenant_id)) is None:
        session.add(
            OrganizationRow(
                id=str(tenant_id),
                name=f"Tenant {str(tenant_id)[:8]}",
                created_at=datetime.now(UTC),
            )
        )
        await session.flush()


def _conversation(row: ConversationRow) -> Conversation:
    return Conversation(
        id=UUID(row.id),
        user_id=UUID(row.user_id),
        title=row.title,
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
    )


def _message(row: MessageRow) -> Message:
    return Message(
        id=UUID(row.id),
        conversation_id=UUID(row.conversation_id),
        role=MessageRole(row.role),
        content=row.content,
        run_id=UUID(row.run_id) if row.run_id else None,
        created_at=_aware(row.created_at),
    )


def _working_session(row: WorkingSessionRow) -> WorkingSession:
    return WorkingSession(
        id=UUID(row.id),
        user_id=UUID(row.user_id),
        title=row.title,
        objective=row.objective,
        workflow_type=row.workflow_type,
        status=WorkingSessionStatus(row.status),
        open_questions=row.open_questions,
        hypotheses=row.hypotheses,
        evidence_ids=[UUID(item) for item in row.evidence_ids],
        artifact_ids=[UUID(item) for item in row.artifact_ids],
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
    )


def _memory(row: MemoryRow) -> Memory:
    return Memory(
        id=UUID(row.id),
        user_id=UUID(row.user_id),
        memory_type=MemoryType(row.memory_type),
        content=row.content,
        normalized_content=row.normalized_content,
        summary=row.summary,
        confidence=row.confidence,
        importance=row.importance,
        status=MemoryStatus(row.status),
        source_type=row.source_type,
        source_id=row.source_id,
        provenance_type=ProvenanceType(row.provenance_type),
        memory_key=row.memory_key,
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
        last_accessed_at=_aware(row.last_accessed_at),
        expires_at=_aware(row.expires_at),
    )


def _relationship(row: MemoryRelationshipRow) -> MemoryRelationship:
    return MemoryRelationship(
        id=UUID(row.id),
        from_memory_id=UUID(row.from_memory_id),
        to_memory_id=UUID(row.to_memory_id),
        relationship_type=MemoryRelationshipType(row.relationship_type),
        created_at=_aware(row.created_at),
    )


class SqlConversationRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, conversation: Conversation) -> Conversation:
        async with self._sessions() as session:
            await _ensure_user(session, conversation.user_id)
            session.add(
                ConversationRow(
                    id=str(conversation.id),
                    user_id=str(conversation.user_id),
                    title=conversation.title,
                    created_at=conversation.created_at,
                    updated_at=conversation.updated_at,
                )
            )
            await session.commit()
        return conversation

    async def get(self, conversation_id: UUID, user_id: UUID) -> ConversationDetail | None:
        async with self._sessions() as session:
            result = await session.execute(
                select(ConversationRow)
                .options(selectinload(ConversationRow.messages))
                .where(
                    ConversationRow.id == str(conversation_id),
                    ConversationRow.user_id == str(user_id),
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return ConversationDetail(
                conversation=_conversation(row), messages=[_message(item) for item in row.messages]
            )

    async def add_message(self, message: Message) -> Message:
        async with self._sessions() as session:
            session.add(
                MessageRow(
                    id=str(message.id),
                    conversation_id=str(message.conversation_id),
                    role=message.role,
                    content=message.content,
                    run_id=str(message.run_id) if message.run_id else None,
                    created_at=message.created_at,
                )
            )
            row = await session.get(ConversationRow, str(message.conversation_id))
            if row is not None:
                row.updated_at = message.created_at
            await session.commit()
        return message


class SqlWorkingSessionRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, item: WorkingSession) -> WorkingSession:
        async with self._sessions() as session:
            await _ensure_user(session, item.user_id)
            session.add(
                WorkingSessionRow(
                    id=str(item.id),
                    user_id=str(item.user_id),
                    title=item.title,
                    objective=item.objective,
                    workflow_type=item.workflow_type,
                    status=item.status,
                    open_questions=item.open_questions,
                    hypotheses=item.hypotheses,
                    evidence_ids=[str(value) for value in item.evidence_ids],
                    artifact_ids=[str(value) for value in item.artifact_ids],
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
            )
            await session.commit()
        return item

    async def get(self, session_id: UUID, user_id: UUID) -> WorkingSession | None:
        async with self._sessions() as session:
            result = await session.execute(
                select(WorkingSessionRow).where(
                    WorkingSessionRow.id == str(session_id),
                    WorkingSessionRow.user_id == str(user_id),
                )
            )
            row = result.scalar_one_or_none()
            return _working_session(row) if row else None

    async def list(
        self, user_id: UUID, status: WorkingSessionStatus | None = None
    ) -> list[WorkingSession]:
        query = select(WorkingSessionRow).where(WorkingSessionRow.user_id == str(user_id))
        if status is not None:
            query = query.where(WorkingSessionRow.status == status)
        query = query.order_by(WorkingSessionRow.updated_at.desc())
        async with self._sessions() as session:
            rows = (await session.execute(query)).scalars().all()
            return [_working_session(row) for row in rows]

    async def attach_artifact(
        self, session_id: UUID, user_id: UUID, artifact_id: UUID, evidence_ids: list[str]
    ) -> None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(WorkingSessionRow).where(
                        WorkingSessionRow.id == str(session_id),
                        WorkingSessionRow.user_id == str(user_id),
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return
            row.artifact_ids = list(dict.fromkeys([*row.artifact_ids, str(artifact_id)]))
            row.evidence_ids = list(dict.fromkeys([*row.evidence_ids, *evidence_ids]))
            row.updated_at = datetime.now(UTC)
            await session.commit()


class SqlArtifactRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, item: Artifact) -> Artifact:
        async with self._sessions() as session:
            await _ensure_user(session, item.user_id)
            await _ensure_organization(session, item.tenant_id)
            session.add(
                ArtifactRow(
                    id=str(item.id),
                    tenant_id=str(item.tenant_id),
                    user_id=str(item.user_id),
                    artifact_type=item.artifact_type,
                    title=item.title,
                    structured_data=item.structured_data,
                    rendered_content=item.rendered_content,
                    workflow_id=str(item.workflow_id),
                    workflow_name=item.workflow_name,
                    workflow_version=item.workflow_version,
                    agent_run_id=str(item.agent_run_id),
                    working_session_id=(
                        str(item.working_session_id) if item.working_session_id else None
                    ),
                    source_ids=item.source_ids,
                    memory_ids=item.memory_ids,
                    model_metadata=item.model_metadata,
                    status=item.status,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
            )
            await session.commit()
        return item

    async def get(self, artifact_id: UUID, tenant_id: UUID, user_id: UUID) -> Artifact | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(ArtifactRow).where(
                        ArtifactRow.id == str(artifact_id),
                        ArtifactRow.tenant_id == str(tenant_id),
                        ArtifactRow.user_id == str(user_id),
                    )
                )
            ).scalar_one_or_none()
            return self._domain(row) if row else None

    async def list(
        self,
        tenant_id: UUID,
        user_id: UUID,
        artifact_type: str | None = None,
        status: ArtifactStatus | None = None,
    ) -> list[Artifact]:
        query = select(ArtifactRow).where(
            ArtifactRow.tenant_id == str(tenant_id), ArtifactRow.user_id == str(user_id)
        )
        if artifact_type:
            query = query.where(ArtifactRow.artifact_type == artifact_type)
        if status:
            query = query.where(ArtifactRow.status == status)
        query = query.order_by(ArtifactRow.updated_at.desc())
        async with self._sessions() as session:
            rows = (await session.execute(query)).scalars().all()
            return [self._domain(row) for row in rows]

    @staticmethod
    def _domain(row: ArtifactRow) -> Artifact:
        return Artifact(
            id=UUID(row.id),
            tenant_id=UUID(row.tenant_id),
            user_id=UUID(row.user_id),
            artifact_type=ArtifactType(row.artifact_type),
            title=row.title,
            structured_data=row.structured_data,
            rendered_content=row.rendered_content,
            workflow_id=UUID(row.workflow_id),
            workflow_name=WorkflowName(row.workflow_name),
            workflow_version=row.workflow_version,
            agent_run_id=UUID(row.agent_run_id),
            working_session_id=(UUID(row.working_session_id) if row.working_session_id else None),
            source_ids=row.source_ids,
            memory_ids=row.memory_ids,
            model_metadata=row.model_metadata,
            status=ArtifactStatus(row.status),
            created_at=_aware(row.created_at),
            updated_at=_aware(row.updated_at),
        )


class SqlManagementRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create_initiative(self, item: Initiative) -> Initiative:
        async with self._sessions() as session:
            await _ensure_user(session, item.user_id)
            await _ensure_organization(session, item.tenant_id)
            session.add(self._initiative_row(item))
            await session.commit()
        return item

    async def update_initiative(self, item: Initiative) -> Initiative:
        async with self._sessions() as session:
            row = await session.get(InitiativeRow, str(item.id))
            if row:
                row.health = [value.model_dump(mode="json") for value in item.health]
                row.updated_at = item.updated_at
                row.status = item.status
            await session.commit()
        return item

    async def get_initiative(
        self, initiative_id: UUID, tenant_id: UUID, user_id: UUID
    ) -> Initiative | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(InitiativeRow).where(
                        InitiativeRow.id == str(initiative_id),
                        InitiativeRow.tenant_id == str(tenant_id),
                        InitiativeRow.user_id == str(user_id),
                    )
                )
            ).scalar_one_or_none()
            return self._initiative(row) if row else None

    async def list_initiatives(self, tenant_id: UUID, user_id: UUID) -> list[Initiative]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(InitiativeRow)
                        .where(
                            InitiativeRow.tenant_id == str(tenant_id),
                            InitiativeRow.user_id == str(user_id),
                        )
                        .order_by(InitiativeRow.updated_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            return [self._initiative(row) for row in rows]

    async def create_outcome(self, item: Outcome) -> Outcome:
        async with self._sessions() as session:
            await _ensure_user(session, item.user_id)
            await _ensure_organization(session, item.tenant_id)
            session.add(
                OutcomeRow(
                    id=str(item.id),
                    tenant_id=str(item.tenant_id),
                    user_id=str(item.user_id),
                    name=item.name,
                    outcome_type=item.outcome_type,
                    baseline=item.baseline,
                    target=item.target,
                    current=item.current,
                    metric=item.metric,
                    owner_ids=item.owner_ids,
                    initiative_ids=[str(value) for value in item.initiative_ids],
                    status=item.status,
                    attribution=item.attribution,
                    evidence_ids=item.evidence_ids,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
            )
            await session.commit()
        return item

    async def list_outcomes(self, tenant_id: UUID, user_id: UUID) -> list[Outcome]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(OutcomeRow).where(
                            OutcomeRow.tenant_id == str(tenant_id),
                            OutcomeRow.user_id == str(user_id),
                        )
                    )
                )
                .scalars()
                .all()
            )
            return [self._outcome(row) for row in rows]

    async def create_commitment(self, item: Commitment) -> Commitment:
        async with self._sessions() as session:
            await _ensure_user(session, item.user_id)
            await _ensure_organization(session, item.tenant_id)
            session.add(self._commitment_row(item))
            await session.commit()
        return item

    async def update_commitment(self, item: Commitment) -> Commitment:
        async with self._sessions() as session:
            row = await session.get(CommitmentRow, str(item.id))
            if row:
                row.due_at = item.due_at
                row.status = item.status
                row.history = [value.model_dump(mode="json") for value in item.history]
                row.updated_at = item.updated_at
            await session.commit()
        return item

    async def get_commitment(
        self, commitment_id: UUID, tenant_id: UUID, user_id: UUID
    ) -> Commitment | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(CommitmentRow).where(
                        CommitmentRow.id == str(commitment_id),
                        CommitmentRow.tenant_id == str(tenant_id),
                        CommitmentRow.user_id == str(user_id),
                    )
                )
            ).scalar_one_or_none()
            return self._commitment(row) if row else None

    async def list_commitments(self, tenant_id: UUID, user_id: UUID) -> list[Commitment]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(CommitmentRow).where(
                            CommitmentRow.tenant_id == str(tenant_id),
                            CommitmentRow.user_id == str(user_id),
                        )
                    )
                )
                .scalars()
                .all()
            )
            return [self._commitment(row) for row in rows]

    async def replace_signals(
        self, tenant_id: UUID, user_id: UUID, signals: list[ManagementSignal]
    ) -> list[ManagementSignal]:
        existing = await self.list_signals(tenant_id, user_id)
        fingerprints = {(item.signal_type, item.subject_id, item.observation) for item in existing}
        async with self._sessions() as session:
            for item in signals:
                fingerprint = (item.signal_type, item.subject_id, item.observation)
                if fingerprint not in fingerprints:
                    session.add(self._signal_row(item))
            await session.commit()
        return await self.list_signals(tenant_id, user_id)

    async def get_signal(
        self, signal_id: UUID, tenant_id: UUID, user_id: UUID
    ) -> ManagementSignal | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(ManagementSignalRow).where(
                        ManagementSignalRow.id == str(signal_id),
                        ManagementSignalRow.tenant_id == str(tenant_id),
                        ManagementSignalRow.user_id == str(user_id),
                    )
                )
            ).scalar_one_or_none()
            return self._signal(row) if row else None

    async def update_signal(self, item: ManagementSignal) -> ManagementSignal:
        async with self._sessions() as session:
            row = await session.get(ManagementSignalRow, str(item.id))
            if row:
                row.status = item.status
                row.interpretation = item.interpretation
                row.limitations = item.limitations
                row.updated_at = item.updated_at
            await session.commit()
        return item

    async def list_signals(self, tenant_id: UUID, user_id: UUID) -> list[ManagementSignal]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(ManagementSignalRow)
                        .where(
                            ManagementSignalRow.tenant_id == str(tenant_id),
                            ManagementSignalRow.user_id == str(user_id),
                        )
                        .order_by(ManagementSignalRow.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            return [self._signal(row) for row in rows]

    async def add_correction(self, item: SignalCorrection) -> SignalCorrection:
        async with self._sessions() as session:
            session.add(
                SignalCorrectionRow(
                    id=str(item.id),
                    signal_id=str(item.signal_id),
                    user_id=str(item.user_id),
                    action=item.action,
                    context=item.context,
                    prior_interpretation=item.prior_interpretation,
                    created_at=item.created_at,
                )
            )
            await session.commit()
        return item

    async def list_corrections(self, signal_id: UUID, user_id: UUID) -> list[SignalCorrection]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(SignalCorrectionRow)
                        .where(
                            SignalCorrectionRow.signal_id == str(signal_id),
                            SignalCorrectionRow.user_id == str(user_id),
                        )
                        .order_by(SignalCorrectionRow.created_at)
                    )
                )
                .scalars()
                .all()
            )
            return [
                SignalCorrection(
                    id=UUID(row.id),
                    signal_id=UUID(row.signal_id),
                    user_id=UUID(row.user_id),
                    action=CorrectionAction(row.action),
                    context=row.context,
                    prior_interpretation=row.prior_interpretation,
                    created_at=_aware(row.created_at),
                )
                for row in rows
            ]

    async def replace_attention(
        self, tenant_id: UUID, user_id: UUID, signals: list[AttentionSignal]
    ) -> list[AttentionSignal]:
        existing = await self.list_attention(tenant_id, user_id)
        fingerprints = {item.management_signal_id for item in existing}
        async with self._sessions() as session:
            for item in signals:
                if item.management_signal_id not in fingerprints:
                    session.add(self._attention_row(item))
            await session.commit()
        return await self.list_attention(tenant_id, user_id)

    async def list_attention(self, tenant_id: UUID, user_id: UUID) -> list[AttentionSignal]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(AttentionSignalRow)
                        .where(
                            AttentionSignalRow.tenant_id == str(tenant_id),
                            AttentionSignalRow.user_id == str(user_id),
                        )
                        .order_by(AttentionSignalRow.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            return [self._attention(row) for row in rows]

    @staticmethod
    def _initiative_row(item: Initiative) -> InitiativeRow:
        return InitiativeRow(
            id=str(item.id),
            tenant_id=str(item.tenant_id),
            user_id=str(item.user_id),
            name=item.name,
            description=item.description,
            problem=item.problem,
            owner_ids=item.owner_ids,
            objective_ids=item.objective_ids,
            status=item.status,
            start_date=(
                datetime.combine(item.start_date, datetime.min.time(), UTC)
                if item.start_date
                else None
            ),
            target_date=(
                datetime.combine(item.target_date, datetime.min.time(), UTC)
                if item.target_date
                else None
            ),
            product_outcomes=item.product_outcomes,
            business_outcomes=item.business_outcomes,
            decision_ids=item.decision_ids,
            evidence_ids=item.evidence_ids,
            artifact_ids=item.artifact_ids,
            jira_issue_ids=item.jira_issue_ids,
            dependency_ids=item.dependency_ids,
            health=[value.model_dump(mode="json") for value in item.health],
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _initiative(row: InitiativeRow) -> Initiative:
        return Initiative(
            id=UUID(row.id),
            tenant_id=UUID(row.tenant_id),
            user_id=UUID(row.user_id),
            name=row.name,
            description=row.description,
            problem=row.problem,
            owner_ids=row.owner_ids,
            objective_ids=row.objective_ids,
            status=InitiativeStatus(row.status),
            start_date=row.start_date.date() if row.start_date else None,
            target_date=row.target_date.date() if row.target_date else None,
            product_outcomes=row.product_outcomes,
            business_outcomes=row.business_outcomes,
            decision_ids=row.decision_ids,
            evidence_ids=row.evidence_ids,
            artifact_ids=row.artifact_ids,
            jira_issue_ids=row.jira_issue_ids,
            dependency_ids=row.dependency_ids,
            health=[InitiativeHealthDimension.model_validate(value) for value in row.health],
            created_at=_aware(row.created_at),
            updated_at=_aware(row.updated_at),
        )

    @staticmethod
    def _outcome(row: OutcomeRow) -> Outcome:
        return Outcome(
            id=UUID(row.id),
            tenant_id=UUID(row.tenant_id),
            user_id=UUID(row.user_id),
            name=row.name,
            outcome_type=OutcomeType(row.outcome_type),
            baseline=row.baseline,
            target=row.target,
            current=row.current,
            metric=row.metric,
            owner_ids=row.owner_ids,
            initiative_ids=[UUID(value) for value in row.initiative_ids],
            status=OutcomeStatus(row.status),
            attribution=AttributionType(row.attribution),
            evidence_ids=row.evidence_ids,
            created_at=_aware(row.created_at),
            updated_at=_aware(row.updated_at),
        )

    @staticmethod
    def _commitment_row(item: Commitment) -> CommitmentRow:
        return CommitmentRow(
            id=str(item.id),
            tenant_id=str(item.tenant_id),
            user_id=str(item.user_id),
            description=item.description,
            owner_id=item.owner_id,
            source=item.source,
            due_at=item.due_at,
            status=item.status,
            initiative_id=str(item.initiative_id) if item.initiative_id else None,
            dependencies=item.dependencies,
            evidence_ids=item.evidence_ids,
            history=[value.model_dump(mode="json") for value in item.history],
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _commitment(row: CommitmentRow) -> Commitment:
        return Commitment(
            id=UUID(row.id),
            tenant_id=UUID(row.tenant_id),
            user_id=UUID(row.user_id),
            description=row.description,
            owner_id=row.owner_id,
            source=row.source,
            due_at=_aware(row.due_at),
            status=CommitmentStatus(row.status),
            initiative_id=UUID(row.initiative_id) if row.initiative_id else None,
            dependencies=row.dependencies,
            evidence_ids=row.evidence_ids,
            history=[CommitmentHistory.model_validate(value) for value in row.history],
            created_at=_aware(row.created_at),
            updated_at=_aware(row.updated_at),
        )

    @staticmethod
    def _signal_row(item: ManagementSignal) -> ManagementSignalRow:
        return ManagementSignalRow(
            id=str(item.id),
            tenant_id=str(item.tenant_id),
            user_id=str(item.user_id),
            signal_type=item.signal_type,
            subject_type=item.subject_type,
            subject_id=item.subject_id,
            epistemic_level=item.epistemic_level,
            observation=item.observation,
            derived_signal=item.derived_signal,
            interpretation=item.interpretation,
            recommendation=item.recommendation,
            evidence_ids=item.evidence_ids,
            confidence=item.confidence,
            significance=item.significance,
            time_window_start=item.time_window_start,
            time_window_end=item.time_window_end,
            limitations=item.limitations,
            status=item.status,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _signal(row: ManagementSignalRow) -> ManagementSignal:
        return ManagementSignal(
            id=UUID(row.id),
            tenant_id=UUID(row.tenant_id),
            user_id=UUID(row.user_id),
            signal_type=SignalType(row.signal_type),
            subject_type=row.subject_type,
            subject_id=row.subject_id,
            epistemic_level=EpistemicLevel(row.epistemic_level),
            observation=row.observation,
            derived_signal=row.derived_signal,
            interpretation=row.interpretation,
            recommendation=row.recommendation,
            evidence_ids=row.evidence_ids,
            confidence=ConfidenceLevel(row.confidence),
            significance=Significance(row.significance),
            time_window_start=_aware(row.time_window_start),
            time_window_end=_aware(row.time_window_end),
            limitations=row.limitations,
            status=SignalStatus(row.status),
            created_at=_aware(row.created_at),
            updated_at=_aware(row.updated_at),
        )

    @staticmethod
    def _attention_row(item: AttentionSignal) -> AttentionSignalRow:
        return AttentionSignalRow(
            id=str(item.id),
            tenant_id=str(item.tenant_id),
            user_id=str(item.user_id),
            management_signal_id=str(item.management_signal_id),
            subject_type=item.subject_type,
            subject_id=item.subject_id,
            level=item.level,
            why_surfaced=item.why_surfaced,
            evidence_ids=item.evidence_ids,
            confidence=item.confidence,
            limitations=item.limitations,
            recommended_next_step=item.recommended_next_step,
            status=item.status,
            created_at=item.created_at,
        )

    @staticmethod
    def _attention(row: AttentionSignalRow) -> AttentionSignal:
        return AttentionSignal(
            id=UUID(row.id),
            tenant_id=UUID(row.tenant_id),
            user_id=UUID(row.user_id),
            management_signal_id=UUID(row.management_signal_id),
            subject_type=row.subject_type,
            subject_id=row.subject_id,
            level=Significance(row.level),
            why_surfaced=row.why_surfaced,
            evidence_ids=row.evidence_ids,
            confidence=ConfidenceLevel(row.confidence),
            limitations=row.limitations,
            recommended_next_step=row.recommended_next_step,
            status=SignalStatus(row.status),
            created_at=_aware(row.created_at),
        )


class SqlProactiveRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create_schedule(self, item: ProactiveSchedule) -> ProactiveSchedule:
        async with self._sessions() as session:
            await _ensure_user(session, item.user_id)
            await _ensure_organization(session, item.tenant_id)
            session.add(self._schedule_row(item))
            await session.commit()
        return item

    async def update_schedule(self, item: ProactiveSchedule) -> ProactiveSchedule:
        async with self._sessions() as session:
            row = await session.get(ProactiveScheduleRow, str(item.id))
            if row:
                row.enabled = item.enabled
                row.timezone = item.timezone
                row.local_time = item.local_time.isoformat()
                row.weekday = item.weekday
                row.next_run_at = item.next_run_at
                row.last_run_at = item.last_run_at
                row.updated_at = item.updated_at
            await session.commit()
        return item

    async def get_schedule(
        self, schedule_id: UUID, tenant_id: UUID, user_id: UUID
    ) -> ProactiveSchedule | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(ProactiveScheduleRow).where(
                        ProactiveScheduleRow.id == str(schedule_id),
                        ProactiveScheduleRow.tenant_id == str(tenant_id),
                        ProactiveScheduleRow.user_id == str(user_id),
                    )
                )
            ).scalar_one_or_none()
            return self._schedule(row) if row else None

    async def list_schedules(self, tenant_id: UUID, user_id: UUID) -> list[ProactiveSchedule]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(ProactiveScheduleRow)
                        .where(
                            ProactiveScheduleRow.tenant_id == str(tenant_id),
                            ProactiveScheduleRow.user_id == str(user_id),
                        )
                        .order_by(ProactiveScheduleRow.next_run_at)
                    )
                )
                .scalars()
                .all()
            )
            return [self._schedule(row) for row in rows]

    async def get_preferences(
        self, tenant_id: UUID, user_id: UUID
    ) -> NotificationPreferences | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(NotificationPreferencesRow).where(
                        NotificationPreferencesRow.tenant_id == str(tenant_id),
                        NotificationPreferencesRow.user_id == str(user_id),
                    )
                )
            ).scalar_one_or_none()
            return self._preferences(row) if row else None

    async def save_preferences(self, item: NotificationPreferences) -> NotificationPreferences:
        async with self._sessions() as session:
            await _ensure_user(session, item.user_id)
            await _ensure_organization(session, item.tenant_id)
            row = (
                await session.execute(
                    select(NotificationPreferencesRow).where(
                        NotificationPreferencesRow.tenant_id == str(item.tenant_id),
                        NotificationPreferencesRow.user_id == str(item.user_id),
                    )
                )
            ).scalar_one_or_none()
            values = self._preferences_values(item)
            if row:
                for key, value in values.items():
                    setattr(row, key, value)
            else:
                session.add(
                    NotificationPreferencesRow(
                        id=str(
                            uuid5(
                                NAMESPACE_URL,
                                f"productos:notification-preferences:{item.tenant_id}:{item.user_id}",
                            )
                        ),
                        tenant_id=str(item.tenant_id),
                        user_id=str(item.user_id),
                        **values,
                    )
                )
            await session.commit()
        return item

    async def get_snapshot(
        self, tenant_id: UUID, user_id: UUID, subject_type: str, subject_id: str
    ) -> ChangeSnapshot | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(ChangeSnapshotRow).where(
                        ChangeSnapshotRow.tenant_id == str(tenant_id),
                        ChangeSnapshotRow.user_id == str(user_id),
                        ChangeSnapshotRow.subject_type == subject_type,
                        ChangeSnapshotRow.subject_id == subject_id,
                    )
                )
            ).scalar_one_or_none()
            return self._snapshot(row) if row else None

    async def save_snapshot(self, item: ChangeSnapshot) -> ChangeSnapshot:
        async with self._sessions() as session:
            await _ensure_user(session, item.user_id)
            await _ensure_organization(session, item.tenant_id)
            row = (
                await session.execute(
                    select(ChangeSnapshotRow).where(
                        ChangeSnapshotRow.tenant_id == str(item.tenant_id),
                        ChangeSnapshotRow.user_id == str(item.user_id),
                        ChangeSnapshotRow.subject_type == item.subject_type,
                        ChangeSnapshotRow.subject_id == item.subject_id,
                    )
                )
            ).scalar_one_or_none()
            if row:
                row.fingerprint = item.fingerprint
                row.state = item.state
                row.observed_at = item.observed_at
            else:
                session.add(
                    ChangeSnapshotRow(
                        id=str(item.id),
                        tenant_id=str(item.tenant_id),
                        user_id=str(item.user_id),
                        subject_type=item.subject_type,
                        subject_id=item.subject_id,
                        fingerprint=item.fingerprint,
                        state=item.state,
                        observed_at=item.observed_at,
                    )
                )
            await session.commit()
        return item

    async def create_notification(
        self, item: ProactiveNotification
    ) -> ProactiveNotification | None:
        async with self._sessions() as session:
            existing = (
                await session.execute(
                    select(ProactiveNotificationRow).where(
                        ProactiveNotificationRow.tenant_id == str(item.tenant_id),
                        ProactiveNotificationRow.user_id == str(item.user_id),
                        ProactiveNotificationRow.dedupe_key == item.dedupe_key,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                return None
            await _ensure_user(session, item.user_id)
            await _ensure_organization(session, item.tenant_id)
            session.add(self._notification_row(item))
            await session.commit()
        return item

    async def update_notification(self, item: ProactiveNotification) -> ProactiveNotification:
        async with self._sessions() as session:
            row = await session.get(ProactiveNotificationRow, str(item.id))
            if row:
                row.status = item.status
                row.read_at = item.read_at
            await session.commit()
        return item

    async def get_notification(
        self, notification_id: UUID, tenant_id: UUID, user_id: UUID
    ) -> ProactiveNotification | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(ProactiveNotificationRow).where(
                        ProactiveNotificationRow.id == str(notification_id),
                        ProactiveNotificationRow.tenant_id == str(tenant_id),
                        ProactiveNotificationRow.user_id == str(user_id),
                    )
                )
            ).scalar_one_or_none()
            return self._notification(row) if row else None

    async def list_notifications(
        self, tenant_id: UUID, user_id: UUID
    ) -> list[ProactiveNotification]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(ProactiveNotificationRow)
                        .where(
                            ProactiveNotificationRow.tenant_id == str(tenant_id),
                            ProactiveNotificationRow.user_id == str(user_id),
                        )
                        .order_by(ProactiveNotificationRow.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            return [self._notification(row) for row in rows]

    @staticmethod
    def _schedule_row(item: ProactiveSchedule) -> ProactiveScheduleRow:
        return ProactiveScheduleRow(
            id=str(item.id),
            tenant_id=str(item.tenant_id),
            user_id=str(item.user_id),
            kind=item.kind,
            frequency=item.frequency,
            enabled=item.enabled,
            timezone=item.timezone,
            local_time=item.local_time.isoformat(),
            weekday=item.weekday,
            next_run_at=item.next_run_at,
            last_run_at=item.last_run_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _schedule(row: ProactiveScheduleRow) -> ProactiveSchedule:
        return ProactiveSchedule(
            id=UUID(row.id),
            tenant_id=UUID(row.tenant_id),
            user_id=UUID(row.user_id),
            kind=ScheduleKind(row.kind),
            frequency=ScheduleFrequency(row.frequency),
            enabled=row.enabled,
            timezone=row.timezone,
            local_time=time.fromisoformat(row.local_time),
            weekday=row.weekday,
            next_run_at=_aware(row.next_run_at),
            last_run_at=_aware(row.last_run_at),
            created_at=_aware(row.created_at),
            updated_at=_aware(row.updated_at),
        )

    @staticmethod
    def _preferences_values(item: NotificationPreferences) -> dict[str, object]:
        return {
            "enabled": item.enabled,
            "in_app_enabled": item.in_app_enabled,
            "daily_brief_enabled": item.daily_brief_enabled,
            "weekly_brief_enabled": item.weekly_brief_enabled,
            "decision_reminders_enabled": item.decision_reminders_enabled,
            "risk_alerts_enabled": item.risk_alerts_enabled,
            "minimum_level": item.minimum_level,
            "maximum_per_day": item.maximum_per_day,
            "quiet_hours_start": item.quiet_hours_start.isoformat()
            if item.quiet_hours_start
            else None,
            "quiet_hours_end": item.quiet_hours_end.isoformat() if item.quiet_hours_end else None,
            "timezone": item.timezone,
            "updated_at": item.updated_at,
        }

    @staticmethod
    def _preferences(row: NotificationPreferencesRow) -> NotificationPreferences:
        return NotificationPreferences(
            tenant_id=UUID(row.tenant_id),
            user_id=UUID(row.user_id),
            enabled=row.enabled,
            in_app_enabled=row.in_app_enabled,
            daily_brief_enabled=row.daily_brief_enabled,
            weekly_brief_enabled=row.weekly_brief_enabled,
            decision_reminders_enabled=row.decision_reminders_enabled,
            risk_alerts_enabled=row.risk_alerts_enabled,
            minimum_level=Significance(row.minimum_level),
            maximum_per_day=row.maximum_per_day,
            quiet_hours_start=time.fromisoformat(row.quiet_hours_start)
            if row.quiet_hours_start
            else None,
            quiet_hours_end=time.fromisoformat(row.quiet_hours_end)
            if row.quiet_hours_end
            else None,
            timezone=row.timezone,
            updated_at=_aware(row.updated_at),
        )

    @staticmethod
    def _snapshot(row: ChangeSnapshotRow) -> ChangeSnapshot:
        return ChangeSnapshot(
            id=UUID(row.id),
            tenant_id=UUID(row.tenant_id),
            user_id=UUID(row.user_id),
            subject_type=row.subject_type,
            subject_id=row.subject_id,
            fingerprint=row.fingerprint,
            state=row.state,
            observed_at=_aware(row.observed_at),
        )

    @staticmethod
    def _notification_row(item: ProactiveNotification) -> ProactiveNotificationRow:
        return ProactiveNotificationRow(
            id=str(item.id),
            tenant_id=str(item.tenant_id),
            user_id=str(item.user_id),
            dedupe_key=item.dedupe_key,
            category=item.category,
            title=item.title,
            body=item.body,
            level=item.level,
            evidence_ids=item.evidence_ids,
            confidence=item.confidence,
            limitations=item.limitations,
            recommended_next_step=item.recommended_next_step,
            related_artifact_id=str(item.related_artifact_id) if item.related_artifact_id else None,
            status=item.status,
            delivery_channel=item.delivery_channel,
            created_at=item.created_at,
            read_at=item.read_at,
        )

    @staticmethod
    def _notification(row: ProactiveNotificationRow) -> ProactiveNotification:
        return ProactiveNotification(
            id=UUID(row.id),
            tenant_id=UUID(row.tenant_id),
            user_id=UUID(row.user_id),
            dedupe_key=row.dedupe_key,
            category=row.category,
            title=row.title,
            body=row.body,
            level=Significance(row.level),
            evidence_ids=row.evidence_ids,
            confidence=ConfidenceLevel(row.confidence),
            limitations=row.limitations,
            recommended_next_step=row.recommended_next_step,
            related_artifact_id=UUID(row.related_artifact_id) if row.related_artifact_id else None,
            status=NotificationStatus(row.status),
            delivery_channel=row.delivery_channel,
            created_at=_aware(row.created_at),
            read_at=_aware(row.read_at),
        )


class SqlMemoryRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def insert(self, item: Memory) -> Memory:
        async with self._sessions() as session:
            await _ensure_user(session, item.user_id)
            session.add(self._row(item))
            await session.commit()
        return item

    async def get(self, memory_id: UUID, user_id: UUID) -> Memory | None:
        async with self._sessions() as session:
            result = await session.execute(
                select(MemoryRow).where(
                    MemoryRow.id == str(memory_id), MemoryRow.user_id == str(user_id)
                )
            )
            row = result.scalar_one_or_none()
            return _memory(row) if row else None

    async def list(
        self,
        user_id: UUID,
        memory_type: MemoryType | None = None,
        status: MemoryStatus | None = None,
        limit: int = 100,
    ) -> list[Memory]:
        query = select(MemoryRow).where(MemoryRow.user_id == str(user_id))
        if memory_type is not None:
            query = query.where(MemoryRow.memory_type == memory_type)
        if status is not None:
            query = query.where(MemoryRow.status == status)
        query = query.order_by(MemoryRow.updated_at.desc()).limit(limit)
        async with self._sessions() as session:
            rows = (await session.execute(query)).scalars().all()
            return [_memory(row) for row in rows]

    async def find_duplicate(
        self, user_id: UUID, memory_type: MemoryType, normalized_content: str
    ) -> Memory | None:
        async with self._sessions() as session:
            result = await session.execute(
                select(MemoryRow).where(
                    MemoryRow.user_id == str(user_id),
                    MemoryRow.memory_type == memory_type,
                    MemoryRow.normalized_content == normalized_content,
                    MemoryRow.status.in_([MemoryStatus.ACTIVE, MemoryStatus.CANDIDATE]),
                )
            )
            row = result.scalar_one_or_none()
            return _memory(row) if row else None

    async def find_active_by_key(
        self, user_id: UUID, memory_type: MemoryType, memory_key: str
    ) -> Memory | None:
        async with self._sessions() as session:
            result = await session.execute(
                select(MemoryRow)
                .where(
                    MemoryRow.user_id == str(user_id),
                    MemoryRow.memory_type == memory_type,
                    MemoryRow.memory_key == memory_key,
                    MemoryRow.status == MemoryStatus.ACTIVE,
                )
                .order_by(MemoryRow.updated_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return _memory(row) if row else None

    async def update(self, item: Memory) -> Memory:
        async with self._sessions() as session:
            row = await session.get(MemoryRow, str(item.id))
            if row is None:
                raise LookupError(f"Memory {item.id} does not exist")
            for name in (
                "content",
                "normalized_content",
                "summary",
                "confidence",
                "importance",
                "status",
                "source_type",
                "source_id",
                "provenance_type",
                "memory_key",
                "updated_at",
                "last_accessed_at",
                "expires_at",
            ):
                setattr(row, name, getattr(item, name))
            await session.commit()
        return item

    async def add_relationship(self, item: MemoryRelationship) -> MemoryRelationship:
        async with self._sessions() as session:
            session.add(
                MemoryRelationshipRow(
                    id=str(item.id),
                    from_memory_id=str(item.from_memory_id),
                    to_memory_id=str(item.to_memory_id),
                    relationship_type=item.relationship_type,
                    created_at=item.created_at,
                )
            )
            await session.commit()
        return item

    async def relationships(
        self, memory_id: UUID
    ) -> tuple[list[MemoryRelationship], list[MemoryRelationship]]:
        async with self._sessions() as session:
            outgoing_rows = (
                (
                    await session.execute(
                        select(MemoryRelationshipRow).where(
                            MemoryRelationshipRow.from_memory_id == str(memory_id)
                        )
                    )
                )
                .scalars()
                .all()
            )
            incoming_rows = (
                (
                    await session.execute(
                        select(MemoryRelationshipRow).where(
                            MemoryRelationshipRow.to_memory_id == str(memory_id)
                        )
                    )
                )
                .scalars()
                .all()
            )
            return (
                [_relationship(row) for row in outgoing_rows],
                [_relationship(row) for row in incoming_rows],
            )

    @staticmethod
    def _row(item: Memory) -> MemoryRow:
        return MemoryRow(
            id=str(item.id),
            user_id=str(item.user_id),
            memory_type=item.memory_type,
            content=item.content,
            normalized_content=item.normalized_content,
            summary=item.summary,
            confidence=item.confidence,
            importance=item.importance,
            status=item.status,
            source_type=item.source_type,
            source_id=item.source_id,
            provenance_type=item.provenance_type,
            memory_key=item.memory_key,
            created_at=item.created_at,
            updated_at=item.updated_at,
            last_accessed_at=item.last_accessed_at,
            expires_at=item.expires_at,
        )


def _decision(row: DecisionRow) -> Decision:
    return Decision(
        id=UUID(row.id),
        user_id=UUID(row.user_id),
        memory_id=UUID(row.memory_id) if row.memory_id else None,
        title=row.title,
        problem=row.problem,
        context=row.context,
        decision=row.decision,
        rationale=row.rationale,
        evidence=row.evidence,
        alternatives=row.alternatives,
        rejected_alternatives=row.rejected_alternatives,
        assumptions=row.assumptions,
        tradeoffs=row.tradeoffs,
        owner=row.owner,
        status=DecisionStatus(row.status),
        review_at=_aware(row.review_at),
        review_trigger=row.review_trigger,
        validation_plan=row.validation_plan,
        created_at=_aware(row.created_at),
        updated_at=_aware(row.updated_at),
    )


class SqlDecisionRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, item: Decision) -> Decision:
        async with self._sessions() as session:
            await _ensure_user(session, item.user_id)
            session.add(
                DecisionRow(
                    id=str(item.id),
                    user_id=str(item.user_id),
                    memory_id=str(item.memory_id) if item.memory_id else None,
                    title=item.title,
                    problem=item.problem,
                    context=item.context,
                    decision=item.decision,
                    rationale=item.rationale,
                    evidence=item.evidence,
                    alternatives=item.alternatives,
                    rejected_alternatives=item.rejected_alternatives,
                    assumptions=item.assumptions,
                    tradeoffs=item.tradeoffs,
                    owner=item.owner,
                    status=item.status,
                    review_at=item.review_at,
                    review_trigger=item.review_trigger,
                    validation_plan=item.validation_plan,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
            )
            await session.commit()
        return item

    async def get(self, decision_id: UUID, user_id: UUID) -> Decision | None:
        async with self._sessions() as session:
            result = await session.execute(
                select(DecisionRow).where(
                    DecisionRow.id == str(decision_id), DecisionRow.user_id == str(user_id)
                )
            )
            row = result.scalar_one_or_none()
            return _decision(row) if row else None

    async def list(self, user_id: UUID) -> list[Decision]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(DecisionRow)
                        .where(DecisionRow.user_id == str(user_id))
                        .order_by(DecisionRow.updated_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            return [_decision(row) for row in rows]

    async def supersede_by_memory(self, memory_id: UUID) -> None:
        async with self._sessions() as session:
            result = await session.execute(
                select(DecisionRow).where(DecisionRow.memory_id == str(memory_id))
            )
            row = result.scalar_one_or_none()
            if row is not None:
                row.status = DecisionStatus.SUPERSEDED
                row.updated_at = datetime.now(UTC)
                await session.commit()


def _belief(row: BeliefRow) -> Belief:
    return Belief(
        id=UUID(row.id),
        memory_id=UUID(row.memory_id),
        statement=row.statement,
        confidence=row.confidence,
        supporting_evidence=row.supporting_evidence,
        contradicting_evidence=row.contradicting_evidence,
        status=BeliefStatus(row.status),
    )


class SqlBeliefRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, item: Belief) -> Belief:
        async with self._sessions() as session:
            session.add(
                BeliefRow(
                    id=str(item.id),
                    memory_id=str(item.memory_id),
                    statement=item.statement,
                    confidence=item.confidence,
                    supporting_evidence=item.supporting_evidence,
                    contradicting_evidence=item.contradicting_evidence,
                    status=item.status,
                )
            )
            await session.commit()
        return item

    async def get(self, belief_id: UUID, user_id: UUID) -> Belief | None:
        async with self._sessions() as session:
            result = await session.execute(
                select(BeliefRow)
                .join(MemoryRow, BeliefRow.memory_id == MemoryRow.id)
                .where(BeliefRow.id == str(belief_id), MemoryRow.user_id == str(user_id))
            )
            row = result.scalar_one_or_none()
            return _belief(row) if row else None

    async def list(self, user_id: UUID) -> list[Belief]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(BeliefRow)
                        .join(MemoryRow, BeliefRow.memory_id == MemoryRow.id)
                        .where(MemoryRow.user_id == str(user_id))
                        .order_by(MemoryRow.updated_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            return [_belief(row) for row in rows]

    async def supersede_by_memory(self, memory_id: UUID) -> None:
        async with self._sessions() as session:
            result = await session.execute(
                select(BeliefRow).where(BeliefRow.memory_id == str(memory_id))
            )
            row = result.scalar_one_or_none()
            if row is not None:
                row.status = BeliefStatus.SUPERSEDED
                await session.commit()


def _knowledge_item(row: KnowledgeItemRow) -> KnowledgeItem:
    return KnowledgeItem(
        id=UUID(row.id),
        tenant_id=UUID(row.tenant_id),
        user_id=UUID(row.user_id),
        source_type=row.source_type,
        source_id=row.source_id,
        title=row.title,
        content=row.content,
        content_checksum=row.content_checksum,
        document_format=DocumentFormat(row.document_format),
        summary=row.summary,
        author=row.author,
        owner=row.owner,
        workspace=row.workspace,
        project=row.project,
        url=row.url,
        source_created_at=_aware(row.source_created_at),
        source_updated_at=_aware(row.source_updated_at),
        ingested_at=_aware(row.ingested_at),
        authority_score=row.authority_score,
        sensitivity=Sensitivity(row.sensitivity),
        access_boundary=row.access_boundary,
        status=KnowledgeStatus(row.status),
        supersedes_id=UUID(row.supersedes_id) if row.supersedes_id else None,
        embedding_provider=row.embedding_provider,
        embedding_dimension=row.embedding_dimension,
        metadata=row.metadata_json,
    )


def _knowledge_chunk(row: KnowledgeChunkRow) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=UUID(row.id),
        knowledge_item_id=UUID(row.knowledge_item_id),
        tenant_id=UUID(row.tenant_id),
        user_id=UUID(row.user_id),
        chunk_index=row.chunk_index,
        content=row.content,
        token_count=row.token_count,
        embedding=list(row.embedding),
        section_title=row.section_title,
        parent_section=row.parent_section,
        metadata=row.metadata_json,
    )


def _cosine_score(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    cosine = dot / (left_norm * right_norm)
    return max(0.0, min(1.0, cosine))


class SqlKnowledgeRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def active_source(
        self, tenant_id: UUID, user_id: UUID, source_type: str, source_id: str
    ) -> KnowledgeItem | None:
        async with self._sessions() as session:
            result = await session.execute(
                select(KnowledgeItemRow)
                .where(
                    KnowledgeItemRow.tenant_id == str(tenant_id),
                    KnowledgeItemRow.user_id == str(user_id),
                    KnowledgeItemRow.source_type == source_type,
                    KnowledgeItemRow.source_id == source_id,
                    KnowledgeItemRow.status == KnowledgeStatus.ACTIVE,
                )
                .order_by(KnowledgeItemRow.ingested_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return _knowledge_item(row) if row else None

    async def create(
        self,
        item: KnowledgeItem,
        chunks: list[KnowledgeChunk],
        superseded_item_id: UUID | None = None,
    ) -> None:
        async with self._sessions() as session:
            await _ensure_user(session, item.user_id)
            await _ensure_organization(session, item.tenant_id)
            if superseded_item_id is not None:
                old = await session.get(KnowledgeItemRow, str(superseded_item_id))
                if old is not None:
                    old.status = KnowledgeStatus.SUPERSEDED
            session.add(
                KnowledgeItemRow(
                    id=str(item.id),
                    tenant_id=str(item.tenant_id),
                    user_id=str(item.user_id),
                    source_type=item.source_type,
                    source_id=item.source_id,
                    title=item.title,
                    content=item.content,
                    content_checksum=item.content_checksum,
                    document_format=item.document_format,
                    summary=item.summary,
                    author=item.author,
                    owner=item.owner,
                    workspace=item.workspace,
                    project=item.project,
                    url=item.url,
                    source_created_at=item.source_created_at,
                    source_updated_at=item.source_updated_at,
                    ingested_at=item.ingested_at,
                    authority_score=item.authority_score,
                    sensitivity=item.sensitivity,
                    access_boundary=item.access_boundary,
                    status=item.status,
                    supersedes_id=str(item.supersedes_id) if item.supersedes_id else None,
                    embedding_provider=item.embedding_provider,
                    embedding_dimension=item.embedding_dimension,
                    metadata_json=item.metadata,
                )
            )
            session.add_all(
                [
                    KnowledgeChunkRow(
                        id=str(chunk.id),
                        knowledge_item_id=str(chunk.knowledge_item_id),
                        tenant_id=str(chunk.tenant_id),
                        user_id=str(chunk.user_id),
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        token_count=chunk.token_count,
                        embedding=chunk.embedding,
                        section_title=chunk.section_title,
                        parent_section=chunk.parent_section,
                        metadata_json=chunk.metadata,
                    )
                    for chunk in chunks
                ]
            )
            await session.commit()

    async def get(
        self, item_id: UUID, tenant_id: UUID, user_id: UUID
    ) -> KnowledgeItemDetail | None:
        async with self._sessions() as session:
            result = await session.execute(
                select(KnowledgeItemRow)
                .options(selectinload(KnowledgeItemRow.chunks))
                .where(
                    KnowledgeItemRow.id == str(item_id),
                    KnowledgeItemRow.tenant_id == str(tenant_id),
                    KnowledgeItemRow.user_id == str(user_id),
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return KnowledgeItemDetail(
                item=_knowledge_item(row),
                chunks=[_knowledge_chunk(chunk) for chunk in row.chunks],
            )

    def _filtered_query(
        self,
        tenant_id: UUID,
        user_id: UUID,
        source_types: list[str],
        projects: list[str],
        updated_after: datetime | None,
    ):
        query = (
            select(KnowledgeChunkRow, KnowledgeItemRow)
            .join(KnowledgeItemRow, KnowledgeChunkRow.knowledge_item_id == KnowledgeItemRow.id)
            .where(
                KnowledgeChunkRow.tenant_id == str(tenant_id),
                KnowledgeChunkRow.user_id == str(user_id),
                KnowledgeItemRow.status == KnowledgeStatus.ACTIVE,
            )
        )
        if source_types:
            query = query.where(KnowledgeItemRow.source_type.in_(source_types))
        if projects:
            query = query.where(KnowledgeItemRow.project.in_(projects))
        if updated_after is not None:
            query = query.where(
                func.coalesce(KnowledgeItemRow.source_updated_at, KnowledgeItemRow.ingested_at)
                >= updated_after
            )
        return query

    async def semantic_search(
        self,
        tenant_id: UUID,
        user_id: UUID,
        query_embedding: list[float],
        source_types: list[str],
        projects: list[str],
        updated_after: datetime | None,
        limit: int,
    ) -> list[RetrievalCandidate]:
        async with self._sessions() as session:
            query = self._filtered_query(tenant_id, user_id, source_types, projects, updated_after)
            if session.bind and session.bind.dialect.name == "postgresql":
                distance = cast(
                    KnowledgeChunkRow.embedding, Vector(len(query_embedding))
                ).cosine_distance(query_embedding)
                rows = (
                    await session.execute(
                        query.add_columns(distance).order_by(distance).limit(limit)
                    )
                ).all()
                return [
                    RetrievalCandidate(
                        chunk=_knowledge_chunk(chunk),
                        item=_knowledge_item(item),
                        semantic_score=max(0.0, min(1.0, 1.0 - float(score))),
                    )
                    for chunk, item, score in rows
                ]
            rows = (await session.execute(query)).all()
            candidates = [
                RetrievalCandidate(
                    chunk=_knowledge_chunk(chunk),
                    item=_knowledge_item(item),
                    semantic_score=_cosine_score(list(chunk.embedding), query_embedding),
                )
                for chunk, item in rows
            ]
            return sorted(candidates, key=lambda value: value.semantic_score, reverse=True)[:limit]

    async def lexical_search(
        self,
        tenant_id: UUID,
        user_id: UUID,
        query_text: str,
        keywords: list[str],
        source_types: list[str],
        projects: list[str],
        updated_after: datetime | None,
        limit: int,
    ) -> list[RetrievalCandidate]:
        async with self._sessions() as session:
            query = self._filtered_query(tenant_id, user_id, source_types, projects, updated_after)
            if session.bind and session.bind.dialect.name == "postgresql":
                vector = func.to_tsvector("english", KnowledgeChunkRow.content)
                terms = func.plainto_tsquery("english", query_text)
                rank = func.ts_rank_cd(vector, terms)
                rows = (
                    await session.execute(
                        query.add_columns(rank)
                        .where(vector.op("@@")(terms))
                        .order_by(rank.desc())
                        .limit(limit)
                    )
                ).all()
                maximum = max((float(row[2]) for row in rows), default=1.0)
                return [
                    RetrievalCandidate(
                        chunk=_knowledge_chunk(chunk),
                        item=_knowledge_item(item),
                        lexical_score=min(1.0, float(score) / maximum) if maximum else 0.0,
                    )
                    for chunk, item, score in rows
                ]
            rows = (await session.execute(query)).all()
            query_terms = set(keywords or re.findall(r"[a-z0-9]+", query_text.casefold()))
            candidates: list[RetrievalCandidate] = []
            for chunk, item in rows:
                terms = set(re.findall(r"[a-z0-9]+", chunk.content.casefold()))
                score = len(query_terms & terms) / max(1, len(query_terms))
                if score:
                    candidates.append(
                        RetrievalCandidate(
                            chunk=_knowledge_chunk(chunk),
                            item=_knowledge_item(item),
                            lexical_score=score,
                        )
                    )
            return sorted(candidates, key=lambda value: value.lexical_score, reverse=True)[:limit]


class SqlTraceRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def append(self, event: TraceEvent) -> None:
        async with self._sessions() as session:
            session.add(
                TraceEventRow(
                    id=str(event.id),
                    run_id=str(event.run_id),
                    event_type=event.event_type,
                    occurred_at=event.occurred_at,
                    attributes=event.attributes,
                )
            )
            await session.commit()

    async def list_for_run(self, run_id: UUID) -> list[TraceEvent]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(TraceEventRow)
                        .where(TraceEventRow.run_id == str(run_id))
                        .order_by(TraceEventRow.occurred_at)
                    )
                )
                .scalars()
                .all()
            )
            return [
                TraceEvent(
                    id=UUID(row.id),
                    run_id=UUID(row.run_id),
                    event_type=TraceEventType(row.event_type),
                    occurred_at=_aware(row.occurred_at),
                    attributes=row.attributes,
                )
                for row in rows
            ]


class SqlAgentRunRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

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
    ) -> None:
        async with self._sessions() as session:
            await _ensure_user(session, state.user_id)
            await _ensure_organization(session, state.tenant_id)
            session.add(
                AgentRunRow(
                    id=str(state.run_id),
                    session_id=str(state.session_id),
                    conversation_id=str(state.conversation_id) if state.conversation_id else None,
                    user_id=str(state.user_id),
                    tenant_id=str(state.tenant_id),
                    request=state.request,
                    intent=state.intent,
                    status=state.status,
                    workflow=workflow,
                    runtime_version=runtime_version,
                    constitution_version=constitution_version,
                    memory_policy_version=memory_policy_version,
                    retrieval_policy_version=retrieval_policy_version,
                    tool_contract_version=tool_contract_version,
                    mcp_adapter_version=mcp_adapter_version,
                    workflow_version=workflow_version,
                    prompt_versions=prompt_versions or {},
                    model=model,
                    response=None,
                    error_type=None,
                    created_at=state.created_at,
                    completed_at=None,
                )
            )
            await session.commit()

    async def complete(self, state: AgentState, error_type: str | None = None) -> None:
        async with self._sessions() as session:
            row = await session.get(AgentRunRow, str(state.run_id))
            if row is None:
                return
            row.status = state.status
            row.response = state.response
            row.error_type = error_type
            row.completed_at = datetime.now(UTC)
            await session.commit()

    async def owns(self, run_id: UUID, tenant_id: UUID, user_id: UUID) -> bool:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(AgentRunRow.id).where(
                        AgentRunRow.id == str(run_id),
                        AgentRunRow.tenant_id == str(tenant_id),
                        AgentRunRow.user_id == str(user_id),
                    )
                )
            ).scalar_one_or_none()
            return row is not None


class SqlToolCallRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, record: ToolCallRecord) -> None:
        async with self._sessions() as session:
            await _ensure_user(session, record.user_id)
            await _ensure_organization(session, record.tenant_id)
            session.add(
                ToolCallRow(
                    id=str(record.id),
                    run_id=str(record.run_id),
                    tenant_id=str(record.tenant_id),
                    user_id=str(record.user_id),
                    workspace_id=record.workspace_id,
                    tool_name=record.tool_name,
                    provider=record.provider,
                    capability=record.capability,
                    input_fingerprint=record.input_fingerprint,
                    status=record.status,
                    error_code=record.error_code,
                    result_count=record.result_count,
                    latency_ms=record.latency_ms,
                    contract_version=record.contract_version,
                    adapter_version=record.adapter_version,
                    started_at=record.started_at,
                    completed_at=record.completed_at,
                )
            )
            await session.commit()

    async def update(self, record: ToolCallRecord) -> None:
        async with self._sessions() as session:
            row = await session.get(ToolCallRow, str(record.id))
            if row is None:
                return
            row.status = record.status
            row.error_code = record.error_code
            row.result_count = record.result_count
            row.latency_ms = record.latency_ms
            row.completed_at = record.completed_at
            await session.commit()


class SqlEvaluationRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create_run(self, item: EvaluationRun) -> EvaluationRun:
        async with self._sessions() as session:
            await _ensure_user(session, item.user_id)
            await _ensure_organization(session, item.tenant_id)
            session.add(self._run_row(item))
            await session.commit()
        return item

    async def add_case(self, item: EvaluationCaseResult) -> EvaluationCaseResult:
        async with self._sessions() as session:
            session.add(
                EvaluationCaseRow(
                    id=str(item.id),
                    evaluation_run_id=str(item.evaluation_run_id),
                    agent_run_id=str(item.agent_run_id) if item.agent_run_id else None,
                    external_id=item.external_id,
                    category=item.category,
                    input_text=item.input_text,
                    expected_behaviors=item.expected_behaviors,
                    forbidden_behaviors=item.forbidden_behaviors,
                    actual_output=item.actual_output,
                    judgment=item.judgment.model_dump(mode="json") if item.judgment else None,
                    status=item.status,
                    error_code=item.error_code,
                    created_at=item.created_at,
                )
            )
            await session.commit()
        return item

    async def update_run(self, item: EvaluationRun) -> EvaluationRun:
        async with self._sessions() as session:
            row = await session.get(EvaluationRunRow, str(item.id))
            if row is not None:
                row.status = item.status
                row.passed_cases = item.passed_cases
                row.failed_cases = item.failed_cases
                row.error_cases = item.error_cases
                row.pass_rate = item.pass_rate
                row.completed_at = item.completed_at
            await session.commit()
        return item

    async def get_run(
        self, run_id: UUID, tenant_id: UUID, user_id: UUID
    ) -> EvaluationRunDetail | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(EvaluationRunRow)
                    .options(selectinload(EvaluationRunRow.cases))
                    .where(
                        EvaluationRunRow.id == str(run_id),
                        EvaluationRunRow.tenant_id == str(tenant_id),
                        EvaluationRunRow.user_id == str(user_id),
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return EvaluationRunDetail(
                run=self._run(row),
                cases=[self._case(item) for item in row.cases],
            )

    async def list_runs(self, tenant_id: UUID, user_id: UUID) -> list[EvaluationRun]:
        async with self._sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(EvaluationRunRow)
                        .where(
                            EvaluationRunRow.tenant_id == str(tenant_id),
                            EvaluationRunRow.user_id == str(user_id),
                        )
                        .order_by(EvaluationRunRow.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            return [self._run(row) for row in rows]

    @staticmethod
    def _run_row(item: EvaluationRun) -> EvaluationRunRow:
        return EvaluationRunRow(
            id=str(item.id),
            tenant_id=str(item.tenant_id),
            user_id=str(item.user_id),
            dataset_name=item.dataset_name,
            dataset_version=item.dataset_version,
            status=item.status,
            subject_model=item.subject_model,
            judge_model=item.judge_model,
            runtime_version=item.runtime_version,
            metrics_version=item.metrics_version,
            total_cases=item.total_cases,
            passed_cases=item.passed_cases,
            failed_cases=item.failed_cases,
            error_cases=item.error_cases,
            pass_rate=item.pass_rate,
            limitation=item.limitation,
            created_at=item.created_at,
            completed_at=item.completed_at,
        )

    @staticmethod
    def _run(row: EvaluationRunRow) -> EvaluationRun:
        return EvaluationRun(
            id=UUID(row.id),
            tenant_id=UUID(row.tenant_id),
            user_id=UUID(row.user_id),
            dataset_name=row.dataset_name,
            dataset_version=row.dataset_version,
            status=EvaluationRunStatus(row.status),
            subject_model=row.subject_model,
            judge_model=row.judge_model,
            runtime_version=row.runtime_version,
            metrics_version=row.metrics_version,
            total_cases=row.total_cases,
            passed_cases=row.passed_cases,
            failed_cases=row.failed_cases,
            error_cases=row.error_cases,
            pass_rate=row.pass_rate,
            limitation=row.limitation,
            created_at=_aware(row.created_at),
            completed_at=_aware(row.completed_at),
        )

    @staticmethod
    def _case(row: EvaluationCaseRow) -> EvaluationCaseResult:
        return EvaluationCaseResult(
            id=UUID(row.id),
            evaluation_run_id=UUID(row.evaluation_run_id),
            agent_run_id=UUID(row.agent_run_id) if row.agent_run_id else None,
            external_id=row.external_id,
            category=row.category,
            input_text=row.input_text,
            expected_behaviors=row.expected_behaviors,
            forbidden_behaviors=row.forbidden_behaviors,
            actual_output=row.actual_output,
            judgment=EvaluationJudgment.model_validate(row.judgment) if row.judgment else None,
            status=EvaluationCaseStatus(row.status),
            error_code=row.error_code,
            created_at=_aware(row.created_at),
        )
