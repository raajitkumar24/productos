from collections.abc import AsyncIterator
from uuid import UUID

import pytest

from productos.application.runtime import AgentRuntime
from productos.config import Settings
from productos.domain.agent import ChatRequest
from productos.infrastructure.tracing import InMemoryTraceRepository


class FailingModel:
    name = "failing-test-model"

    async def generate(self, prompt: str) -> str:
        raise RuntimeError

    async def generate_structured(self, prompt: str, schema: type) -> object:
        raise RuntimeError

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        if False:
            yield ""
        raise RuntimeError("provider secret must not leak")


@pytest.mark.asyncio
async def test_runtime_returns_safe_error_and_traces_failure() -> None:
    traces = InMemoryTraceRepository()
    runtime = AgentRuntime(FailingModel(), traces, Settings())

    events = [event async for event in runtime.stream_chat(ChatRequest(message="hello"))]

    assert events[-1].event == "error"
    assert events[-1].data["message"] == "The model could not complete this request."
    assert "secret" not in str(events[-1].data)
    stored = await traces.list_for_run(UUID(events[0].data["run_id"]))
    assert stored[-1].event_type == "run.failed"
    assert stored[-1].attributes["error_type"] == "RuntimeError"
