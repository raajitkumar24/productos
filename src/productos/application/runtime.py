from collections.abc import AsyncIterator
from typing import Any, Literal

from pydantic import BaseModel, Field

from productos.application.context import ContextPlanner, render_prompt
from productos.application.ports import LanguageModel, TraceRepository
from productos.application.repositories import (
    AgentRunRepository,
    ConversationRepository,
)
from productos.atlassian.service import OrganizationService
from productos.config import Settings
from productos.domain.agent import AgentState, ChatRequest, RunStatus
from productos.domain.conversation import Conversation, Message, MessageRole
from productos.domain.knowledge import EvidencePacket, KnowledgeSearchRequest
from productos.domain.tools import PermissionContext
from productos.domain.trace import TraceEvent, TraceEventType
from productos.memory.extraction import ExplicitMemoryExtractor
from productos.memory.service import MemoryService
from productos.retrieval.service import HybridRetrievalService, render_evidence_prompt


class StreamEvent(BaseModel):
    event: Literal["run", "tool", "evidence", "delta", "complete", "error"]
    data: dict[str, Any] = Field(default_factory=dict)


class AgentRuntime:
    """Application-owned state machine for the persistent chat workflow."""

    def __init__(
        self,
        model: LanguageModel,
        traces: TraceRepository,
        settings: Settings,
        conversations: ConversationRepository | None = None,
        context_planner: ContextPlanner | None = None,
        memory_service: MemoryService | None = None,
        memory_extractor: ExplicitMemoryExtractor | None = None,
        runs: AgentRunRepository | None = None,
        retrieval: HybridRetrievalService | None = None,
        organization: OrganizationService | None = None,
    ) -> None:
        self._model = model
        self._traces = traces
        self._settings = settings
        self._conversations = conversations
        self._context_planner = context_planner
        self._memory_service = memory_service
        self._memory_extractor = memory_extractor
        self._runs = runs
        self._retrieval = retrieval
        self._organization = organization

    @staticmethod
    def _needs_live_organization(request: str) -> bool:
        lowered = request.casefold()
        return any(
            phrase in lowered
            for phrase in ("current state", "currently blocked", "what is blocked", "status of")
        )

    async def _trace(
        self, state: AgentState, event_type: TraceEventType, **attributes: Any
    ) -> None:
        await self._traces.append(
            TraceEvent(run_id=state.run_id, event_type=event_type, attributes=attributes)
        )

    async def stream_chat(
        self, request: ChatRequest, persist_conversation: bool = True
    ) -> AsyncIterator[StreamEvent]:
        state = AgentState.from_request(
            request,
            self._settings.default_user_id,
            self._settings.default_tenant_id,
        )
        user_message: Message | None = None
        if self._conversations is not None and persist_conversation:
            if state.conversation_id is None:
                conversation = Conversation(
                    user_id=state.user_id,
                    title=state.request.strip().replace("\n", " ")[:80],
                )
                await self._conversations.create(conversation)
                state.conversation_id = conversation.id
            elif await self._conversations.get(state.conversation_id, state.user_id) is None:
                yield StreamEvent(
                    event="error",
                    data={
                        "run_id": str(state.run_id),
                        "code": "CONVERSATION_NOT_FOUND",
                        "message": "The requested conversation was not found for this user.",
                    },
                )
                return
            user_message = Message(
                conversation_id=state.conversation_id,
                role=MessageRole.USER,
                content=state.request,
                run_id=state.run_id,
            )
            await self._conversations.add_message(user_message)
        state.status = RunStatus.RUNNING
        live_organization = self._organization is not None and self._needs_live_organization(
            state.request
        )
        workflow = "organization.current_state.v1" if live_organization else "chat.v4"
        if self._runs is not None:
            await self._runs.start(
                state=state,
                workflow=workflow,
                model=self._model.name,
                runtime_version=self._settings.runtime_version,
                constitution_version=self._settings.constitution_version,
                memory_policy_version=self._settings.memory_policy_version,
                retrieval_policy_version=self._settings.retrieval_policy_version,
                tool_contract_version=self._settings.tool_contract_version,
                mcp_adapter_version=self._settings.mcp_adapter_version,
            )
        await self._trace(
            state,
            TraceEventType.RUN_STARTED,
            runtime_version=self._settings.runtime_version,
            constitution_version=self._settings.constitution_version,
        )
        yield StreamEvent(
            event="run",
            data={
                "run_id": str(state.run_id),
                "session_id": str(state.session_id),
                "conversation_id": str(state.conversation_id) if state.conversation_id else None,
                "runtime_version": self._settings.runtime_version,
            },
        )

        try:
            await self._trace(state, TraceEventType.INTENT_CLASSIFIED, intent=state.intent)
            await self._trace(state, TraceEventType.WORKFLOW_SELECTED, workflow=workflow)
            prompt = state.request
            evidence_packet: EvidencePacket | None = None
            if self._context_planner is not None:
                await self._trace(state, TraceEventType.CONTEXT_BUILD_STARTED)
                await self._trace(state, TraceEventType.MEMORY_SEARCH_STARTED)
                context = await self._context_planner.plan(state.user_id, state.request)
                state.memories = [
                    {
                        "memory_id": str(item.memory_id),
                        "score": item.score,
                        "token_estimate": item.token_estimate,
                    }
                    for item in context.items
                ]
                await self._trace(
                    state,
                    TraceEventType.MEMORY_SEARCH_COMPLETED,
                    candidates_considered=context.candidates_considered,
                    selected_count=len(context.items),
                )
                await self._trace(
                    state,
                    TraceEventType.CONTEXT_BUILD_COMPLETED,
                    memory_ids=[str(item.memory_id) for item in context.items],
                    token_estimate=context.token_estimate,
                )
                prompt = render_prompt(state.request, context)
            if live_organization and self._organization is not None:
                await self._trace(
                    state,
                    TraceEventType.RETRIEVAL_STARTED,
                    policy_version=self._settings.retrieval_policy_version,
                    strategy="index_plus_live",
                )
                organization_result = await self._organization.current_state(
                    state.run_id,
                    state.request,
                    PermissionContext(
                        tenant_id=state.tenant_id,
                        user_id=state.user_id,
                        workspace_id=request.workspace_id,
                        permissions=(
                            {"atlassian:read"} if self._settings.atlassian_read_enabled else set()
                        ),
                    ),
                    cloud_id=request.workspace_id,
                )
                evidence_packet = organization_result.evidence
                state.tool_calls = organization_result.tool_calls
                yield StreamEvent(event="tool", data={"calls": state.tool_calls})
            elif self._retrieval is not None:
                await self._trace(
                    state,
                    TraceEventType.RETRIEVAL_STARTED,
                    policy_version=self._settings.retrieval_policy_version,
                )
                evidence_packet = await self._retrieval.search(
                    KnowledgeSearchRequest(
                        query=state.request,
                        limit=self._settings.retrieval_limit,
                    ),
                    state.tenant_id,
                    state.user_id,
                )
            if evidence_packet is not None:
                state.retrieved_context = [
                    {
                        "evidence_id": item.id,
                        "knowledge_item_id": (
                            str(item.knowledge_item_id) if item.knowledge_item_id else None
                        ),
                        "chunk_id": str(item.chunk_id) if item.chunk_id else None,
                        "relevance": item.relevance,
                    }
                    for item in evidence_packet.evidence
                ]
                await self._trace(
                    state,
                    TraceEventType.RETRIEVAL_COMPLETED,
                    availability=evidence_packet.availability,
                    candidate_count=len(evidence_packet.evidence),
                    contradiction_count=len(evidence_packet.contradictions),
                )
                await self._trace(
                    state,
                    TraceEventType.EVIDENCE_PACKET_CREATED,
                    evidence_ids=[item.id for item in evidence_packet.evidence],
                    source_coverage=evidence_packet.source_coverage,
                    known_unknowns=evidence_packet.known_unknowns,
                )
                prompt = render_evidence_prompt(prompt, evidence_packet)
                yield StreamEvent(
                    event="evidence",
                    data=evidence_packet.model_dump(mode="json"),
                )
            await self._trace(state, TraceEventType.MODEL_STREAM_STARTED, model=self._model.name)

            chunks: list[str] = []
            async for chunk in self._model.stream(prompt):
                chunks.append(chunk)
                yield StreamEvent(event="delta", data={"text": chunk})

            state.response = "".join(chunks)
            await self._trace(
                state,
                TraceEventType.MODEL_STREAM_COMPLETED,
                model=self._model.name,
                character_count=len(state.response),
            )
            if self._conversations is not None and state.conversation_id and state.response.strip():
                await self._conversations.add_message(
                    Message(
                        conversation_id=state.conversation_id,
                        role=MessageRole.ASSISTANT,
                        content=state.response.strip(),
                        run_id=state.run_id,
                    )
                )

            memory_updates: list[dict[str, str]] = []
            try:
                if (
                    self._memory_extractor is not None
                    and self._memory_service is not None
                    and user_message is not None
                ):
                    candidates = self._memory_extractor.extract(
                        state.user_id, state.request, str(user_message.id)
                    )
                    await self._trace(
                        state,
                        TraceEventType.MEMORY_CANDIDATES_EXTRACTED,
                        candidate_count=len(candidates),
                        extractor="explicit.v1",
                    )
                    for candidate in candidates:
                        result = await self._memory_service.remember(candidate)
                        memory_updates.append(
                            {"memory_id": str(result.memory.id), "outcome": result.outcome}
                        )
                    await self._trace(
                        state,
                        TraceEventType.MEMORY_WRITE_COMPLETED,
                        outcomes=memory_updates,
                        policy_version=self._settings.memory_policy_version,
                    )
            except Exception as memory_error:
                await self._trace(
                    state,
                    TraceEventType.MEMORY_WRITE_COMPLETED,
                    outcomes=[],
                    error_type=type(memory_error).__name__,
                    policy_version=self._settings.memory_policy_version,
                )
            state.status = RunStatus.COMPLETED
            await self._trace(state, TraceEventType.RUN_COMPLETED, status=state.status)
            if self._runs is not None:
                await self._runs.complete(state)
            yield StreamEvent(
                event="complete",
                data={
                    "run_id": str(state.run_id),
                    "status": state.status,
                    "trace_url": f"/v1/runs/{state.run_id}/traces",
                    "conversation_id": str(state.conversation_id)
                    if state.conversation_id
                    else None,
                    "memory_updates": memory_updates,
                    "tool_calls": state.tool_calls,
                    "citations": (
                        [citation.model_dump(mode="json") for citation in evidence_packet.citations]
                        if evidence_packet is not None
                        else []
                    ),
                },
            )
        except Exception as exc:
            state.status = RunStatus.FAILED
            await self._trace(
                state,
                TraceEventType.RUN_FAILED,
                error_type=type(exc).__name__,
            )
            if self._runs is not None:
                await self._runs.complete(state, error_type=type(exc).__name__)
            yield StreamEvent(
                event="error",
                data={
                    "run_id": str(state.run_id),
                    "code": "MODEL_ERROR",
                    "message": "The model could not complete this request.",
                },
            )
