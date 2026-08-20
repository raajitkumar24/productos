import asyncio
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from time import monotonic
from typing import Protocol
from uuid import UUID

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from productos.application.ports import MCPClientError, TraceRepository
from productos.application.repositories import ToolCallRepository
from productos.domain.tools import (
    PermissionContext,
    ToolCallRecord,
    ToolCallStatus,
    ToolDefinition,
    ToolErrorCode,
    ToolResult,
)
from productos.domain.trace import TraceEvent, TraceEventType
from productos.tools.registry import ToolRegistry


class ToolProvider(Protocol):
    async def execute(
        self, tool_name: str, arguments: dict[str, object], context: PermissionContext
    ) -> object: ...


class CapabilityResolver:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def resolve(self, capability: str, provider: str | None = None) -> ToolDefinition:
        matches = [
            tool
            for tool in self._registry.list()
            if tool.capability == capability and (provider is None or tool.provider == provider)
        ]
        if len(matches) != 1:
            raise LookupError(
                f"Capability {capability!r} resolved to {len(matches)} tools; selection is unsafe."
            )
        return matches[0]


class PermissionEngine:
    def check(self, tool: ToolDefinition, context: PermissionContext) -> ToolErrorCode | None:
        if not tool.required_permissions.issubset(context.permissions):
            return ToolErrorCode.AUTHORIZATION_FAILED
        if not tool.read_only and (tool.requires_confirmation and not context.confirmed):
            return ToolErrorCode.AUTHORIZATION_FAILED
        return None


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        providers: dict[str, ToolProvider],
        permissions: PermissionEngine,
        traces: TraceRepository,
        repository: ToolCallRepository | None,
        contract_version: str,
        adapter_version: str,
        max_tool_calls: int,
        max_retries: int,
        max_latency_seconds: float,
        max_iterations: int = 3,
    ) -> None:
        self._registry = registry
        self._providers = providers
        self._permissions = permissions
        self._traces = traces
        self._repository = repository
        self._contract_version = contract_version
        self._adapter_version = adapter_version
        self._max_calls = max_tool_calls
        self._max_retries = max_retries
        self._max_latency = max_latency_seconds
        self._max_iterations = max_iterations
        self._calls: dict[UUID, int] = defaultdict(int)
        self._fingerprints: dict[UUID, set[str]] = defaultdict(set)

    async def execute(
        self,
        run_id: UUID,
        tool_name: str,
        arguments: dict[str, object],
        context: PermissionContext,
        iteration: int = 1,
    ) -> ToolResult:
        definition = self._registry.get(tool_name)
        if definition is None:
            return ToolResult(
                call_id=UUID(int=0),
                tool_name=tool_name,
                status=ToolCallStatus.FAILED,
                error_code=ToolErrorCode.TOOL_UNAVAILABLE,
                message="The requested tool is not registered.",
            )
        fingerprint = hashlib.sha256(
            json.dumps(
                {"tool": tool_name, "arguments": arguments}, sort_keys=True, default=str
            ).encode()
        ).hexdigest()
        record = ToolCallRecord(
            run_id=run_id,
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            workspace_id=context.workspace_id,
            tool_name=definition.name,
            provider=definition.provider,
            capability=definition.capability,
            input_fingerprint=fingerprint,
            status=ToolCallStatus.STARTED,
            contract_version=self._contract_version,
            adapter_version=self._adapter_version,
        )
        if self._repository:
            await self._repository.create(record)
        await self._trace(
            run_id,
            TraceEventType.TOOL_SELECTED,
            tool_name=tool_name,
            capability=definition.capability,
        )
        if self._calls[run_id] >= self._max_calls:
            return await self._fail(record, ToolErrorCode.BUDGET_EXCEEDED, "Tool budget exceeded.")
        if iteration < 1 or iteration > self._max_iterations:
            return await self._fail(
                record, ToolErrorCode.BUDGET_EXCEEDED, "Tool iteration budget exceeded."
            )
        if fingerprint in self._fingerprints[run_id]:
            return await self._fail(
                record, ToolErrorCode.DUPLICATE_CALL, "Equivalent tool call already executed."
            )
        permission_error = self._permissions.check(definition, context)
        await self._trace(
            run_id,
            TraceEventType.TOOL_PERMISSION_CHECKED,
            tool_name=tool_name,
            allowed=permission_error is None,
            read_only=definition.read_only,
        )
        if permission_error:
            return await self._fail(record, permission_error, "Tool permission denied.")
        try:
            Draft202012Validator(definition.input_schema).validate(arguments)
        except ValidationError:
            return await self._fail(
                record,
                ToolErrorCode.INVALID_ARGUMENT,
                "Tool arguments did not match the contract.",
            )

        self._calls[run_id] += 1
        self._fingerprints[run_id].add(fingerprint)
        await self._trace(run_id, TraceEventType.TOOL_CALL_STARTED, tool_name=tool_name)
        started = monotonic()
        provider = self._providers.get(definition.provider)
        if provider is None:
            return await self._fail(
                record, ToolErrorCode.TOOL_UNAVAILABLE, "The tool provider is unavailable."
            )
        for attempt in range(self._max_retries + 1):
            try:
                timeout = min(definition.timeout_seconds, self._max_latency)
                async with asyncio.timeout(timeout):
                    data = await provider.execute(tool_name, arguments, context)
                count = self._result_count(data)
                record.status = ToolCallStatus.SUCCEEDED
                record.result_count = count
                record.latency_ms = int((monotonic() - started) * 1_000)
                record.completed_at = datetime.now(UTC)
                if self._repository:
                    await self._repository.update(record)
                await self._trace(
                    run_id,
                    TraceEventType.TOOL_CALL_COMPLETED,
                    tool_name=tool_name,
                    result_count=count,
                    latency_ms=record.latency_ms,
                )
                return ToolResult(
                    call_id=record.id,
                    tool_name=tool_name,
                    status=record.status,
                    data=data,
                    result_count=count,
                    latency_ms=record.latency_ms,
                )
            except TimeoutError:
                return await self._fail(record, ToolErrorCode.TIMEOUT, "The tool call timed out.")
            except MCPClientError as exc:
                retryable = exc.code in {ToolErrorCode.RATE_LIMITED, ToolErrorCode.UPSTREAM_ERROR}
                if retryable and attempt < self._max_retries:
                    continue
                return await self._fail(record, exc.code, exc.safe_message)
            except (TypeError, ValueError):
                return await self._fail(
                    record, ToolErrorCode.INVALID_ARGUMENT, "The tool arguments were invalid."
                )
            except Exception:
                return await self._fail(
                    record, ToolErrorCode.UPSTREAM_ERROR, "The tool provider returned an error."
                )
        return await self._fail(record, ToolErrorCode.UPSTREAM_ERROR, "Tool call failed.")

    async def _fail(self, record: ToolCallRecord, code: ToolErrorCode, message: str) -> ToolResult:
        record.status = ToolCallStatus.FAILED
        record.error_code = code
        record.completed_at = datetime.now(UTC)
        if self._repository:
            await self._repository.update(record)
        await self._trace(
            record.run_id,
            TraceEventType.TOOL_CALL_FAILED,
            tool_name=record.tool_name,
            error_code=code,
        )
        return ToolResult(
            call_id=record.id,
            tool_name=record.tool_name,
            status=record.status,
            error_code=code,
            message=message,
        )

    async def _trace(self, run_id: UUID, event_type: TraceEventType, **values: object) -> None:
        await self._traces.append(
            TraceEvent(run_id=run_id, event_type=event_type, attributes=values)
        )

    @staticmethod
    def _result_count(data: object) -> int:
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            for key in ("issues", "pages", "sites", "results"):
                value = data.get(key)
                if isinstance(value, list):
                    return len(value)
        return 1 if data is not None else 0
