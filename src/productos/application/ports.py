from collections.abc import AsyncIterator
from typing import Protocol
from uuid import UUID

from productos.domain.tools import ToolErrorCode
from productos.domain.trace import TraceEvent


class LanguageModel(Protocol):
    @property
    def name(self) -> str: ...

    async def generate(self, prompt: str) -> str: ...

    async def generate_structured(self, prompt: str, schema: type) -> object: ...

    def stream(self, prompt: str) -> AsyncIterator[str]: ...


class TraceRepository(Protocol):
    async def append(self, event: TraceEvent) -> None: ...

    async def list_for_run(self, run_id: UUID) -> list[TraceEvent]: ...


class EmbeddingProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    async def embed_text(self, text: str) -> list[float]: ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class MCPClientError(Exception):
    def __init__(self, code: ToolErrorCode, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


class MCPClient(Protocol):
    async def call_tool(
        self, provider: str, tool_name: str, arguments: dict[str, object]
    ) -> object: ...
