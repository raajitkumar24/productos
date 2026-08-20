import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from productos.application.context import ContextPlanner
from productos.application.ports import MCPClient
from productos.application.runtime import AgentRuntime
from productos.atlassian import AtlassianReadProvider, AtlassianSiteResolver, OrganizationService
from productos.config import Settings, get_settings
from productos.domain.agent import ChatRequest
from productos.domain.atlassian import CurrentStateRequest, SpecExecutionRequest
from productos.domain.conversation import WorkingSession, WorkingSessionCreate, WorkingSessionStatus
from productos.domain.evaluation import EvaluationRunCreate
from productos.domain.knowledge import (
    KnowledgeIngestRequest,
    KnowledgeIngestResult,
    KnowledgeItemDetail,
    KnowledgeSearchRequest,
)
from productos.domain.management import (
    CommitmentCreate,
    CommitmentPatch,
    InitiativeCreate,
    ManagementWorkflowRequest,
    OutcomeCreate,
    SignalCorrectionCreate,
)
from productos.domain.memory import (
    Belief,
    BeliefCreate,
    BeliefStatus,
    Decision,
    DecisionCreate,
    DecisionStatus,
    MemoryCandidate,
    MemoryCreate,
    MemoryPatch,
    MemoryStatus,
    MemoryType,
    ProvenanceType,
)
from productos.domain.proactive import (
    NotificationPatch,
    NotificationPreferencesPatch,
    ScheduleCreate,
    ScheduleKind,
    SchedulePatch,
    SchedulerRunRequest,
)
from productos.domain.tools import PermissionContext, ToolCallStatus
from productos.domain.workflow import ArtifactStatus, WorkflowExecuteRequest
from productos.evaluation import evaluation_catalogs
from productos.evaluation_service import (
    AgentRuntimeEvaluationSubject,
    JudgeNotConfiguredError,
    RepresentativeEvaluationService,
)
from productos.infrastructure.database import create_engine, create_session_factory
from productos.infrastructure.persistence import (
    Base,
    SqlAgentRunRepository,
    SqlArtifactRepository,
    SqlBeliefRepository,
    SqlConversationRepository,
    SqlDecisionRepository,
    SqlEvaluationRepository,
    SqlKnowledgeRepository,
    SqlManagementRepository,
    SqlMemoryRepository,
    SqlProactiveRepository,
    SqlToolCallRepository,
    SqlTraceRepository,
    SqlWorkingSessionRepository,
)
from productos.infrastructure.providers import (
    embedding_provider_from_settings,
    judge_model_from_settings,
    language_model_from_settings,
)
from productos.knowledge import KnowledgeIngestionService, MarkdownTextParser, SectionChunker
from productos.management import ManagementService
from productos.mcp import StreamableHTTPMCPClient, UnavailableMCPClient
from productos.memory import ExplicitMemoryExtractor, MemoryService
from productos.proactive import ProactiveLeadershipService
from productos.retrieval import HybridRetrievalService
from productos.security import (
    AuthenticationError,
    OIDCTokenValidator,
    TokenValidator,
    current_principal,
)
from productos.tools import PermissionEngine, ToolExecutor, atlassian_tool_registry
from productos.workflows import WorkflowRuntime

UserQuery = Annotated[UUID | None, Query()]
TenantQuery = Annotated[UUID | None, Query()]
WorkStatusQuery = Annotated[WorkingSessionStatus | None, Query(alias="status")]
MemoryTypeQuery = Annotated[MemoryType | None, Query()]
MemoryStatusQuery = Annotated[MemoryStatus | None, Query(alias="status")]
LimitQuery = Annotated[int, Query(ge=1, le=500)]
ArtifactStatusQuery = Annotated[ArtifactStatus | None, Query(alias="status")]


def _user_id(value: UUID | None, settings: Settings) -> UUID:
    principal = current_principal.get()
    if principal is not None:
        if value is not None and value != principal.user_id:
            raise HTTPException(status_code=403, detail="User scope does not match bearer token")
        return principal.user_id
    return value or settings.default_user_id


def _tenant_id(value: UUID | None, settings: Settings) -> UUID:
    principal = current_principal.get()
    if principal is not None:
        if value is not None and value != principal.tenant_id:
            raise HTTPException(status_code=403, detail="Tenant scope does not match bearer token")
        return principal.tenant_id
    return value or settings.default_tenant_id


def create_app(
    settings: Settings | None = None,
    mcp_client: MCPClient | None = None,
    token_validator: TokenValidator | None = None,
) -> FastAPI:
    configured = settings or get_settings()
    configured_token_validator = token_validator
    if configured.auth_enabled and configured_token_validator is None:
        configured_token_validator = OIDCTokenValidator(configured)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(configured.database_url)
        if configured.database_auto_create:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        sessions = create_session_factory(engine)
        conversations = SqlConversationRepository(sessions)
        work = SqlWorkingSessionRepository(sessions)
        memories = SqlMemoryRepository(sessions)
        decisions = SqlDecisionRepository(sessions)
        beliefs = SqlBeliefRepository(sessions)
        traces = SqlTraceRepository(sessions)
        runs = SqlAgentRunRepository(sessions)
        tool_calls = SqlToolCallRepository(sessions)
        artifacts = SqlArtifactRepository(sessions)
        knowledge = SqlKnowledgeRepository(sessions)
        memory_service = MemoryService(memories)
        model = language_model_from_settings(configured)
        judge_model = judge_model_from_settings(configured)
        embeddings = embedding_provider_from_settings(configured)
        ingestion = KnowledgeIngestionService(
            knowledge,
            MarkdownTextParser(),
            SectionChunker(
                configured.knowledge_chunk_tokens,
                configured.knowledge_chunk_overlap_tokens,
            ),
            embeddings,
        )
        retrieval = HybridRetrievalService(knowledge, embeddings)
        registry = atlassian_tool_registry()
        configured_mcp_client = mcp_client
        if configured_mcp_client is None and configured.atlassian_mcp_url:
            configured_mcp_client = StreamableHTTPMCPClient(configured.atlassian_mcp_url)
        atlassian_provider = AtlassianReadProvider(
            configured_mcp_client or UnavailableMCPClient(),
            configured.atlassian_mcp_tool_map,
        )
        tool_executor = ToolExecutor(
            registry=registry,
            providers={"atlassian": atlassian_provider},
            permissions=PermissionEngine(),
            traces=traces,
            repository=tool_calls,
            contract_version=configured.tool_contract_version,
            adapter_version=configured.mcp_adapter_version,
            max_tool_calls=configured.max_tool_calls,
            max_retries=configured.max_tool_retries,
            max_latency_seconds=configured.max_tool_latency_seconds,
            max_iterations=configured.max_tool_iterations,
        )
        organization = OrganizationService(
            tool_executor,
            AtlassianSiteResolver(tool_executor),
            indexed=retrieval,
        )
        workflow_runtime = WorkflowRuntime(
            artifacts=artifacts,
            traces=traces,
            settings=configured,
            runs=runs,
            retrieval=retrieval,
            organization=organization,
            work=work,
        )
        management_repository = SqlManagementRepository(sessions)
        management = ManagementService(
            repository=management_repository,
            decisions=decisions,
            artifacts=artifacts,
            runs=runs,
            traces=traces,
            settings=configured,
        )
        proactive_repository = SqlProactiveRepository(sessions)
        proactive = ProactiveLeadershipService(
            repository=proactive_repository,
            management=management,
            artifacts=artifacts,
            runs=runs,
            traces=traces,
            settings=configured,
        )
        runtime = AgentRuntime(
            model=model,
            traces=traces,
            settings=configured,
            conversations=conversations,
            context_planner=ContextPlanner(memories),
            memory_service=memory_service,
            memory_extractor=ExplicitMemoryExtractor(),
            runs=runs,
            retrieval=retrieval,
            organization=organization,
        )
        evaluation_repository = SqlEvaluationRepository(sessions)
        evaluations = RepresentativeEvaluationService(
            evaluation_repository,
            AgentRuntimeEvaluationSubject(runtime, model.name),
            judge_model,
            configured,
        )

        app.state.settings = configured
        app.state.engine = engine
        app.state.conversations = conversations
        app.state.work = work
        app.state.memories = memories
        app.state.decisions = decisions
        app.state.beliefs = beliefs
        app.state.memory_service = memory_service
        app.state.traces = traces
        app.state.runs = runs
        app.state.knowledge = knowledge
        app.state.ingestion = ingestion
        app.state.retrieval = retrieval
        app.state.embeddings = embeddings
        app.state.model = model
        app.state.judge_model = judge_model
        app.state.tool_registry = registry
        app.state.tool_executor = tool_executor
        app.state.organization = organization
        app.state.artifacts = artifacts
        app.state.workflow_runtime = workflow_runtime
        app.state.management_repository = management_repository
        app.state.management = management
        app.state.proactive_repository = proactive_repository
        app.state.proactive = proactive
        app.state.evaluation_repository = evaluation_repository
        app.state.evaluations = evaluations
        app.state.atlassian_transport_configured = configured_mcp_client is not None
        app.state.runtime = runtime
        yield
        for provider in (model, judge_model, embeddings):
            if provider is None:
                continue
            close = getattr(provider, "aclose", None)
            if close is not None:
                await close()
        if configured_token_validator is not None:
            close = getattr(configured_token_validator, "aclose", None)
            if close is not None:
                await close()
        await engine.dispose()

    application = FastAPI(title="ProductOS API", version="0.8.0", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configured.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def authenticate(request: Request, call_next):
        if not configured.auth_enabled or not request.url.path.startswith("/v1/"):
            return await call_next(request)
        authorization = request.headers.get("authorization", "")
        scheme, _, bearer = authorization.partition(" ")
        if scheme.casefold() != "bearer" or not bearer:
            return JSONResponse(
                status_code=401,
                content={"detail": "A bearer token is required"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            if configured_token_validator is None:
                raise AuthenticationError("Authentication validator is unavailable")
            principal = await configured_token_validator.validate(bearer)
        except AuthenticationError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Bearer token validation failed"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        if (
            request.method == "POST"
            and request.url.path == "/v1/proactive/run"
            and not principal.scopes.intersection({"productos:scheduler", "productos:admin"})
        ):
            return JSONResponse(status_code=403, content={"detail": "Scheduler scope required"})
        if (
            request.method == "POST"
            and request.url.path == "/v1/evaluations/run"
            and not principal.scopes.intersection({"productos:evaluator", "productos:admin"})
        ):
            return JSONResponse(status_code=403, content={"detail": "Evaluator scope required"})
        context_token = current_principal.set(principal)
        try:
            return await call_next(request)
        finally:
            current_principal.reset(context_token)

    def get_runtime(request: Request) -> AgentRuntime:
        return request.app.state.runtime

    @application.get("/health")
    async def health(request: Request) -> dict[str, str]:
        current: Settings = request.app.state.settings
        return {
            "status": "ok",
            "service": "productos-api",
            "environment": current.environment,
            "runtime_version": current.runtime_version,
            "memory_policy_version": current.memory_policy_version,
            "retrieval_policy_version": current.retrieval_policy_version,
            "embedding_provider": request.app.state.embeddings.name,
            "model_provider": request.app.state.model.name,
            "evaluation_runner": (
                "ready" if request.app.state.evaluations.ready else "not_configured"
            ),
            "tool_contract_version": current.tool_contract_version,
            "mcp_adapter_version": current.mcp_adapter_version,
            "atlassian": (
                "read_enabled"
                if current.atlassian_read_enabled
                and request.app.state.atlassian_transport_configured
                else "disconnected"
            ),
            "storage": current.database_url.split(":", 1)[0],
        }

    @application.post("/v1/chat", response_class=StreamingResponse)
    async def chat(
        payload: ChatRequest,
        runtime: Annotated[AgentRuntime, Depends(get_runtime)],
    ) -> StreamingResponse:
        payload = payload.model_copy(
            update={
                "user_id": _user_id(payload.user_id, configured),
                "tenant_id": _tenant_id(payload.tenant_id, configured),
            }
        )

        async def event_stream() -> AsyncIterator[str]:
            async for event in runtime.stream_chat(payload):
                yield f"event: {event.event}\ndata: {json.dumps(event.data, default=str)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @application.get("/v1/auth/me")
    async def authenticated_identity() -> object:
        principal = current_principal.get()
        if principal is None:
            return {
                "authentication": "development_disabled",
                "user_id": configured.default_user_id,
                "tenant_id": configured.default_tenant_id,
                "scopes": [],
            }
        return {"authentication": "oidc", **principal.model_dump(mode="json")}

    def permission_context(
        tenant_id: UUID, user_id: UUID, workspace_id: str | None = None
    ) -> PermissionContext:
        return PermissionContext(
            tenant_id=tenant_id,
            user_id=user_id,
            workspace_id=workspace_id,
            permissions={"atlassian:read"} if configured.atlassian_read_enabled else set(),
        )

    @application.get("/v1/tools")
    async def list_tools(request: Request) -> dict[str, object]:
        connected = (
            configured.atlassian_read_enabled and request.app.state.atlassian_transport_configured
        )
        return {
            "connection_status": "read_enabled" if connected else "disconnected",
            "tools": [
                definition.model_dump(mode="json")
                for definition in request.app.state.tool_registry.list()
            ],
        }

    @application.get("/v1/atlassian/sites")
    async def list_atlassian_sites(
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> object:
        result = await request.app.state.tool_executor.execute(
            uuid4(),
            "atlassian.list_sites",
            {},
            permission_context(_tenant_id(tenant_id, configured), _user_id(user_id, configured)),
        )
        if result.status != ToolCallStatus.SUCCEEDED:
            raise HTTPException(status_code=503, detail=result.message)
        return result.data

    @application.post("/v1/organization/current-state")
    async def organization_current_state(payload: CurrentStateRequest, request: Request) -> object:
        result = await request.app.state.organization.current_state(
            uuid4(),
            payload.topic,
            permission_context(
                _tenant_id(payload.tenant_id, configured),
                _user_id(payload.user_id, configured),
                payload.cloud_id,
            ),
            cloud_id=payload.cloud_id,
        )
        return {
            "current_state": result.current_state.model_dump(mode="json"),
            "evidence": result.evidence.model_dump(mode="json"),
            "tool_calls": result.tool_calls,
        }

    @application.post("/v1/organization/search")
    async def organization_search(payload: CurrentStateRequest, request: Request) -> object:
        return await request.app.state.organization.search(
            uuid4(),
            payload.topic,
            permission_context(
                _tenant_id(payload.tenant_id, configured),
                _user_id(payload.user_id, configured),
                payload.cloud_id,
            ),
            cloud_id=payload.cloud_id,
        )

    @application.post("/v1/organization/compare-spec-execution")
    async def compare_spec_execution(payload: SpecExecutionRequest, request: Request) -> object:
        try:
            result = await request.app.state.organization.compare_spec_execution(
                uuid4(),
                payload.page_id,
                permission_context(
                    _tenant_id(payload.tenant_id, configured),
                    _user_id(payload.user_id, configured),
                    payload.cloud_id,
                ),
                cloud_id=payload.cloud_id,
                projects=payload.projects,
            )
        except Exception as exc:
            safe_message = getattr(
                exc, "safe_message", "Comparison evidence could not be retrieved."
            )
            raise HTTPException(status_code=409, detail=safe_message) from exc
        return result

    @application.get("/v1/workflows")
    async def list_workflows(request: Request) -> list[object]:
        return [
            item.model_dump(mode="json")
            for item in request.app.state.workflow_runtime.definitions()
        ]

    @application.post("/v1/workflows/execute", status_code=status.HTTP_201_CREATED)
    async def execute_workflow(payload: WorkflowExecuteRequest, request: Request) -> object:
        try:
            return await request.app.state.workflow_runtime.execute(
                payload,
                _tenant_id(payload.tenant_id, configured),
                _user_id(payload.user_id, configured),
            )
        except Exception as exc:
            safe_message = getattr(exc, "safe_message", "The workflow could not complete.")
            raise HTTPException(status_code=409, detail=safe_message) from exc

    @application.get("/v1/artifacts")
    async def list_artifacts(
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
        artifact_type: str | None = None,
        artifact_status: ArtifactStatusQuery = None,
    ) -> list[object]:
        return await request.app.state.artifacts.list(
            _tenant_id(tenant_id, configured),
            _user_id(user_id, configured),
            artifact_type,
            artifact_status,
        )

    @application.get("/v1/artifacts/{artifact_id}")
    async def get_artifact(
        artifact_id: UUID,
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> object:
        artifact = await request.app.state.artifacts.get(
            artifact_id,
            _tenant_id(tenant_id, configured),
            _user_id(user_id, configured),
        )
        if artifact is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return artifact

    @application.post(
        "/v1/knowledge/ingest",
        status_code=status.HTTP_201_CREATED,
    )
    async def ingest_knowledge(
        payload: KnowledgeIngestRequest, request: Request
    ) -> KnowledgeIngestResult:
        return await request.app.state.ingestion.ingest(
            payload,
            _tenant_id(payload.tenant_id, configured),
            _user_id(payload.user_id, configured),
        )

    @application.post("/v1/knowledge/search")
    async def search_knowledge(payload: KnowledgeSearchRequest, request: Request) -> object:
        return await request.app.state.retrieval.search(
            payload,
            _tenant_id(payload.tenant_id, configured),
            _user_id(payload.user_id, configured),
        )

    @application.get("/v1/knowledge/items/{item_id}")
    async def get_knowledge_item(
        item_id: UUID,
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> KnowledgeItemDetail:
        item = await request.app.state.knowledge.get(
            item_id,
            _tenant_id(tenant_id, configured),
            _user_id(user_id, configured),
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Knowledge item not found")
        return item

    @application.get("/v1/runs/{run_id}/traces")
    async def run_traces(
        run_id: UUID,
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> dict[str, object]:
        if not await request.app.state.runs.owns(
            run_id,
            _tenant_id(tenant_id, configured),
            _user_id(user_id, configured),
        ):
            raise HTTPException(status_code=404, detail="Run not found")
        events = await request.app.state.traces.list_for_run(run_id)
        return {
            "run_id": str(run_id),
            "events": [event.model_dump(mode="json") for event in events],
        }

    @application.get("/v1/sessions/{conversation_id}")
    async def get_conversation(
        conversation_id: UUID,
        request: Request,
        user_id: UserQuery = None,
    ) -> object:
        detail = await request.app.state.conversations.get(
            conversation_id, _user_id(user_id, configured)
        )
        if detail is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return detail

    @application.get("/v1/work")
    async def list_work(
        request: Request,
        user_id: UserQuery = None,
        work_status: WorkStatusQuery = None,
    ) -> list[WorkingSession]:
        return await request.app.state.work.list(_user_id(user_id, configured), status=work_status)

    @application.post("/v1/work", status_code=status.HTTP_201_CREATED)
    async def create_work(payload: WorkingSessionCreate, request: Request) -> WorkingSession:
        session = WorkingSession(
            user_id=_user_id(payload.user_id, configured),
            title=payload.title,
            objective=payload.objective,
            workflow_type=payload.workflow_type,
            open_questions=payload.open_questions,
            hypotheses=payload.hypotheses,
        )
        return await request.app.state.work.create(session)

    @application.get("/v1/work/{session_id}")
    async def get_work(
        session_id: UUID,
        request: Request,
        user_id: UserQuery = None,
    ) -> WorkingSession:
        session = await request.app.state.work.get(session_id, _user_id(user_id, configured))
        if session is None:
            raise HTTPException(status_code=404, detail="Working session not found")
        return session

    @application.get("/v1/memories")
    async def list_memories(
        request: Request,
        user_id: UserQuery = None,
        memory_type: MemoryTypeQuery = None,
        memory_status: MemoryStatusQuery = None,
        limit: LimitQuery = 100,
    ) -> list[object]:
        return await request.app.state.memories.list(
            user_id=_user_id(user_id, configured),
            memory_type=memory_type,
            status=memory_status,
            limit=limit,
        )

    @application.get("/v1/memories/{memory_id}")
    async def get_memory(
        memory_id: UUID,
        request: Request,
        user_id: UserQuery = None,
    ) -> object:
        result = await request.app.state.memory_service.inspect(
            memory_id, _user_id(user_id, configured)
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        return result

    @application.post("/v1/memories", status_code=status.HTTP_201_CREATED)
    async def create_memory(payload: MemoryCreate, request: Request) -> object:
        values = payload.model_dump(
            exclude={"user_id", "provenance_type", "source_type", "source_id"}
        )
        candidate = MemoryCandidate(
            **values,
            user_id=_user_id(payload.user_id, configured),
            provenance_type=ProvenanceType.EXPLICIT_USER,
            source_type="user_api",
        )
        return await request.app.state.memory_service.remember(candidate)

    @application.patch("/v1/memories/{memory_id}")
    async def patch_memory(
        memory_id: UUID,
        payload: MemoryPatch,
        request: Request,
        user_id: UserQuery = None,
    ) -> object:
        result = await request.app.state.memory_service.patch(
            memory_id, _user_id(user_id, configured), payload
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        return result

    @application.get("/v1/decisions")
    async def list_decisions(request: Request, user_id: UserQuery = None) -> list[Decision]:
        return await request.app.state.decisions.list(_user_id(user_id, configured))

    @application.post("/v1/decisions", status_code=status.HTTP_201_CREATED)
    async def create_decision(payload: DecisionCreate, request: Request) -> Decision:
        resolved_user = _user_id(payload.user_id, configured)
        memory_id = None
        if payload.status == DecisionStatus.ACCEPTED:
            remembered = await request.app.state.memory_service.remember(
                MemoryCandidate(
                    user_id=resolved_user,
                    memory_type=MemoryType.DECISION,
                    content=f"{payload.title}: {payload.decision}",
                    summary=payload.rationale[:1_000],
                    confidence=1.0,
                    importance=0.9,
                    source_type="decision_api",
                    provenance_type=ProvenanceType.EXPLICIT_USER,
                    memory_key=f"decision:{payload.title.casefold().strip()}",
                )
            )
            memory_id = remembered.memory.id
            if remembered.related_memory_id is not None:
                await request.app.state.decisions.supersede_by_memory(remembered.related_memory_id)
        decision = Decision(
            **payload.model_dump(exclude={"user_id"}),
            user_id=resolved_user,
            memory_id=memory_id,
        )
        return await request.app.state.decisions.create(decision)

    @application.get("/v1/decisions/{decision_id}")
    async def get_decision(
        decision_id: UUID,
        request: Request,
        user_id: UserQuery = None,
    ) -> Decision:
        decision = await request.app.state.decisions.get(decision_id, _user_id(user_id, configured))
        if decision is None:
            raise HTTPException(status_code=404, detail="Decision not found")
        return decision

    @application.get("/v1/beliefs")
    async def list_beliefs(request: Request, user_id: UserQuery = None) -> list[Belief]:
        return await request.app.state.beliefs.list(_user_id(user_id, configured))

    @application.post("/v1/beliefs", status_code=status.HTTP_201_CREATED)
    async def create_belief(payload: BeliefCreate, request: Request) -> Belief:
        resolved_user = _user_id(payload.user_id, configured)
        remembered = await request.app.state.memory_service.remember(
            MemoryCandidate(
                user_id=resolved_user,
                memory_type=MemoryType.BELIEF,
                content=payload.statement,
                summary=payload.statement[:1_000],
                confidence=payload.confidence,
                importance=0.65,
                source_type="belief_api",
                provenance_type=ProvenanceType.EXPLICIT_USER,
                memory_key=(
                    f"belief:{payload.belief_key.casefold().strip()}"
                    if payload.belief_key
                    else None
                ),
            )
        )
        if remembered.related_memory_id is not None:
            await request.app.state.beliefs.supersede_by_memory(remembered.related_memory_id)
        belief = Belief(
            memory_id=remembered.memory.id,
            statement=payload.statement,
            confidence=payload.confidence,
            supporting_evidence=payload.supporting_evidence,
            contradicting_evidence=payload.contradicting_evidence,
            status=(
                BeliefStatus.ACTIVE
                if remembered.memory.status == MemoryStatus.ACTIVE
                else BeliefStatus.WEAKENED
            ),
        )
        return await request.app.state.beliefs.create(belief)

    @application.get("/v1/beliefs/{belief_id}")
    async def get_belief(
        belief_id: UUID,
        request: Request,
        user_id: UserQuery = None,
    ) -> Belief:
        belief = await request.app.state.beliefs.get(belief_id, _user_id(user_id, configured))
        if belief is None:
            raise HTTPException(status_code=404, detail="Belief not found")
        return belief

    @application.post("/v1/initiatives", status_code=status.HTTP_201_CREATED)
    async def create_initiative(payload: InitiativeCreate, request: Request) -> object:
        return await request.app.state.management.create_initiative(
            payload,
            _tenant_id(payload.tenant_id, configured),
            _user_id(payload.user_id, configured),
        )

    @application.get("/v1/initiatives")
    async def list_initiatives(
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> list[object]:
        return await request.app.state.management.list_initiatives(
            _tenant_id(tenant_id, configured), _user_id(user_id, configured)
        )

    @application.get("/v1/initiatives/{initiative_id}")
    async def get_initiative(
        initiative_id: UUID,
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> object:
        item = await request.app.state.management.get_initiative(
            initiative_id,
            _tenant_id(tenant_id, configured),
            _user_id(user_id, configured),
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Initiative not found")
        return item

    @application.post("/v1/outcomes", status_code=status.HTTP_201_CREATED)
    async def create_outcome(payload: OutcomeCreate, request: Request) -> object:
        return await request.app.state.management.create_outcome(
            payload,
            _tenant_id(payload.tenant_id, configured),
            _user_id(payload.user_id, configured),
        )

    @application.get("/v1/outcomes")
    async def list_outcomes(
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> list[object]:
        return await request.app.state.management_repository.list_outcomes(
            _tenant_id(tenant_id, configured), _user_id(user_id, configured)
        )

    @application.post("/v1/commitments", status_code=status.HTTP_201_CREATED)
    async def create_commitment(payload: CommitmentCreate, request: Request) -> object:
        return await request.app.state.management.create_commitment(
            payload,
            _tenant_id(payload.tenant_id, configured),
            _user_id(payload.user_id, configured),
        )

    @application.get("/v1/commitments")
    async def list_commitments(
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> list[object]:
        return await request.app.state.management_repository.list_commitments(
            _tenant_id(tenant_id, configured), _user_id(user_id, configured)
        )

    @application.patch("/v1/commitments/{commitment_id}")
    async def patch_commitment(
        commitment_id: UUID,
        payload: CommitmentPatch,
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> object:
        item = await request.app.state.management.patch_commitment(
            commitment_id,
            payload,
            _tenant_id(tenant_id, configured),
            _user_id(user_id, configured),
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Commitment not found")
        return item

    @application.post("/v1/management/refresh")
    async def refresh_management(
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> object:
        signals, attention = await request.app.state.management.refresh_intelligence(
            _tenant_id(tenant_id, configured), _user_id(user_id, configured)
        )
        return {"signals": signals, "attention": attention}

    @application.get("/v1/management/signals")
    async def list_management_signals(
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> list[object]:
        return await request.app.state.management_repository.list_signals(
            _tenant_id(tenant_id, configured), _user_id(user_id, configured)
        )

    @application.post("/v1/management/signals/{signal_id}/corrections")
    async def correct_management_signal(
        signal_id: UUID,
        payload: SignalCorrectionCreate,
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> object:
        result = await request.app.state.management.correct_signal(
            signal_id,
            payload,
            _tenant_id(tenant_id, configured),
            _user_id(user_id, configured),
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Management signal not found")
        signal, correction = result
        return {"signal": signal, "correction": correction}

    @application.get("/v1/management/signals/{signal_id}/corrections")
    async def list_signal_corrections(
        signal_id: UUID, request: Request, user_id: UserQuery = None
    ) -> list[object]:
        return await request.app.state.management_repository.list_corrections(
            signal_id, _user_id(user_id, configured)
        )

    @application.get("/v1/attention")
    async def list_attention(
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> list[object]:
        return await request.app.state.management.attention(
            _tenant_id(tenant_id, configured), _user_id(user_id, configured)
        )

    @application.get("/v1/team")
    async def list_team(
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
        weeks: int = Query(default=4, ge=1, le=52),
    ) -> list[object]:
        resolved_tenant = _tenant_id(tenant_id, configured)
        resolved_user = _user_id(user_id, configured)
        initiatives = await request.app.state.management.list_initiatives(
            resolved_tenant, resolved_user
        )
        owners = sorted({owner for item in initiatives for owner in item.owner_ids})
        payload = ManagementWorkflowRequest(weeks=weeks)
        return [
            await request.app.state.management.profile(
                owner, resolved_tenant, resolved_user, payload.window_start
            )
            for owner in owners
        ]

    @application.get("/v1/team/{pm_id}")
    async def get_team_member(
        pm_id: str,
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
        weeks: int = Query(default=4, ge=1, le=52),
    ) -> object:
        return await request.app.state.management.profile(
            pm_id,
            _tenant_id(tenant_id, configured),
            _user_id(user_id, configured),
            ManagementWorkflowRequest(weeks=weeks).window_start,
        )

    @application.post("/v1/management/one-on-one")
    async def prepare_one_on_one(payload: ManagementWorkflowRequest, request: Request) -> object:
        if not payload.pm_id:
            raise HTTPException(status_code=422, detail="pm_id is required")
        brief, artifact = await request.app.state.management.one_on_one(
            payload.pm_id,
            _tenant_id(payload.tenant_id, configured),
            _user_id(payload.user_id, configured),
            payload.window_start,
        )
        return {"brief": brief, "artifact": artifact}

    @application.post("/v1/management/pm-review")
    async def prepare_pm_review(payload: ManagementWorkflowRequest, request: Request) -> object:
        if not payload.pm_id:
            raise HTTPException(status_code=422, detail="pm_id is required")
        review, artifact = await request.app.state.management.pm_review(
            payload.pm_id,
            _tenant_id(payload.tenant_id, configured),
            _user_id(payload.user_id, configured),
            payload.window_start,
        )
        return {"review": review, "artifact": artifact}

    @application.post("/v1/management/weekly-review")
    async def prepare_weekly_review(payload: ManagementWorkflowRequest, request: Request) -> object:
        review, artifact = await request.app.state.management.weekly_review(
            _tenant_id(payload.tenant_id, configured),
            _user_id(payload.user_id, configured),
            payload.window_start,
        )
        return {"review": review, "artifact": artifact}

    @application.post("/v1/management/portfolio-review")
    async def prepare_portfolio_review(
        payload: ManagementWorkflowRequest, request: Request
    ) -> object:
        review, artifact = await request.app.state.management.portfolio_review(
            _tenant_id(payload.tenant_id, configured),
            _user_id(payload.user_id, configured),
        )
        return {"review": review, "artifact": artifact}

    @application.get("/v1/management/decision-debt")
    async def list_decision_debt(request: Request, user_id: UserQuery = None) -> list[object]:
        return await request.app.state.management.decision_debt(_user_id(user_id, configured))

    @application.get("/v1/proactive/schedules")
    async def list_proactive_schedules(
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> list[object]:
        return await request.app.state.proactive_repository.list_schedules(
            _tenant_id(tenant_id, configured), _user_id(user_id, configured)
        )

    @application.post("/v1/proactive/schedules", status_code=status.HTTP_201_CREATED)
    async def create_proactive_schedule(payload: ScheduleCreate, request: Request) -> object:
        try:
            return await request.app.state.proactive.create_schedule(
                payload,
                _tenant_id(payload.tenant_id, configured),
                _user_id(payload.user_id, configured),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.patch("/v1/proactive/schedules/{schedule_id}")
    async def patch_proactive_schedule(
        schedule_id: UUID,
        payload: SchedulePatch,
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> object:
        try:
            item = await request.app.state.proactive.patch_schedule(
                schedule_id,
                payload,
                _tenant_id(tenant_id, configured),
                _user_id(user_id, configured),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if item is None:
            raise HTTPException(status_code=404, detail="Proactive schedule not found")
        return item

    @application.get("/v1/proactive/preferences")
    async def get_notification_preferences(
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> object:
        return await request.app.state.proactive.preferences(
            _tenant_id(tenant_id, configured), _user_id(user_id, configured)
        )

    @application.patch("/v1/proactive/preferences")
    async def patch_notification_preferences(
        payload: NotificationPreferencesPatch,
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> object:
        try:
            return await request.app.state.proactive.patch_preferences(
                payload,
                _tenant_id(tenant_id, configured),
                _user_id(user_id, configured),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post("/v1/proactive/run")
    async def run_proactive_scheduler(payload: SchedulerRunRequest, request: Request) -> object:
        return await request.app.state.proactive.run(
            _tenant_id(payload.tenant_id, configured),
            _user_id(payload.user_id, configured),
            payload.now,
            payload.force_kinds,
        )

    @application.post("/v1/proactive/daily-brief")
    async def generate_daily_product_brief(
        payload: SchedulerRunRequest, request: Request
    ) -> object:
        brief, artifact, changes = await request.app.state.proactive.daily_brief(
            _tenant_id(payload.tenant_id, configured),
            _user_id(payload.user_id, configured),
            payload.now,
        )
        return {"brief": brief, "artifact": artifact, "changes": changes}

    @application.post("/v1/proactive/risk-scan")
    async def run_proactive_risk_scan(payload: SchedulerRunRequest, request: Request) -> object:
        changes, notifications, suppressed = await request.app.state.proactive.scan(
            _tenant_id(payload.tenant_id, configured),
            _user_id(payload.user_id, configured),
            payload.now,
            ScheduleKind.RISK_SCAN,
        )
        return {
            "changes": changes,
            "notifications": notifications,
            "suppressed": suppressed,
        }

    @application.get("/v1/proactive/notifications")
    async def list_proactive_notifications(
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> list[object]:
        return await request.app.state.proactive.notifications(
            _tenant_id(tenant_id, configured), _user_id(user_id, configured)
        )

    @application.patch("/v1/proactive/notifications/{notification_id}")
    async def patch_proactive_notification(
        notification_id: UUID,
        payload: NotificationPatch,
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> object:
        item = await request.app.state.proactive.patch_notification(
            notification_id,
            payload,
            _tenant_id(tenant_id, configured),
            _user_id(user_id, configured),
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Proactive notification not found")
        return item

    @application.get("/v1/home")
    async def get_home(
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> object:
        return await request.app.state.proactive.home(
            _tenant_id(tenant_id, configured), _user_id(user_id, configured)
        )

    @application.get("/v1/evaluations/catalogs")
    async def list_evaluation_catalogs() -> object:
        return evaluation_catalogs()

    @application.get("/v1/evaluations")
    async def list_evaluation_runs(
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> list[object]:
        return await request.app.state.evaluations.list(
            _tenant_id(tenant_id, configured), _user_id(user_id, configured)
        )

    @application.get("/v1/evaluations/{run_id}")
    async def get_evaluation_run(
        run_id: UUID,
        request: Request,
        user_id: UserQuery = None,
        tenant_id: TenantQuery = None,
    ) -> object:
        item = await request.app.state.evaluations.get(
            run_id,
            _tenant_id(tenant_id, configured),
            _user_id(user_id, configured),
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Evaluation run not found")
        return item

    @application.post("/v1/evaluations/run", status_code=status.HTTP_201_CREATED)
    async def execute_evaluation_run(payload: EvaluationRunCreate, request: Request) -> object:
        try:
            return await request.app.state.evaluations.execute(
                payload,
                _tenant_id(payload.tenant_id, configured),
                _user_id(payload.user_id, configured),
            )
        except JudgeNotConfiguredError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return application


app = create_app()
