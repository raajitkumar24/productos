import json
from collections.abc import AsyncIterator

import httpx
from pydantic import BaseModel

from productos.application.ports import EmbeddingProvider, LanguageModel
from productos.config import Settings
from productos.infrastructure.model import DevelopmentLanguageModel
from productos.knowledge import DeterministicEmbeddingProvider


class ModelProviderError(RuntimeError):
    """Safe provider failure that never includes credentials or raw response bodies."""


class OpenAICompatibleLanguageModel:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60,
        max_output_tokens: int = 4096,
        temperature: float = 0.1,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._model = model
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(timeout_seconds),
        )

    @property
    def name(self) -> str:
        return f"openai-compatible:{self._model}"

    def _payload(self, prompt: str, stream: bool = False) -> dict[str, object]:
        return {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._temperature,
            "max_tokens": self._max_output_tokens,
            "stream": stream,
        }

    async def generate(self, prompt: str) -> str:
        return await self._generate_payload(self._payload(prompt))

    async def generate_structured(self, prompt: str, schema: type) -> object:
        payload = self._payload(prompt)
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": True,
                    "schema": schema.model_json_schema(),
                },
            }
        text = await self._generate_payload(payload)
        try:
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                return schema.model_validate_json(text)
            return json.loads(text)
        except (ValueError, TypeError) as exc:
            raise ModelProviderError("The model returned invalid structured output.") from exc

    async def _generate_payload(self, payload: dict[str, object]) -> str:
        try:
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            body = response.json()
            return str(body["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise ModelProviderError("The configured model provider failed safely.") from exc

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        try:
            async with self._client.stream(
                "POST", "/chat/completions", json=self._payload(prompt, stream=True)
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        return
                    event = json.loads(data)
                    content = event.get("choices", [{}])[0].get("delta", {}).get("content")
                    if content:
                        yield str(content)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise ModelProviderError("The configured model provider stream failed safely.") from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class OpenAICompatibleEmbeddingProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dimension: int,
        timeout_seconds: float = 60,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._model = model
        self._dimension = dimension
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(timeout_seconds),
        )

    @property
    def name(self) -> str:
        return f"openai-compatible:{self._model}"

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_text(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            response = await self._client.post(
                "/embeddings", json={"model": self._model, "input": texts}
            )
            response.raise_for_status()
            records = sorted(response.json()["data"], key=lambda item: item["index"])
            vectors = [[float(value) for value in item["embedding"]] for item in records]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ModelProviderError("The configured embedding provider failed safely.") from exc
        if len(vectors) != len(texts) or any(len(vector) != self._dimension for vector in vectors):
            raise ModelProviderError("The embedding provider returned an unexpected dimension.")
        return vectors

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def language_model_from_settings(settings: Settings) -> LanguageModel:
    if settings.model_provider == "development":
        return DevelopmentLanguageModel()
    return OpenAICompatibleLanguageModel(
        base_url=str(settings.model_base_url),
        api_key=settings.model_api_key.get_secret_value() if settings.model_api_key else "",
        model=str(settings.model_name),
        timeout_seconds=settings.model_timeout_seconds,
        max_output_tokens=settings.model_max_output_tokens,
        temperature=settings.model_temperature,
    )


def embedding_provider_from_settings(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "deterministic":
        return DeterministicEmbeddingProvider(settings.embedding_dimension)
    api_key = settings.embedding_api_key or settings.model_api_key
    return OpenAICompatibleEmbeddingProvider(
        base_url=str(settings.embedding_base_url or settings.model_base_url),
        api_key=api_key.get_secret_value() if api_key else "",
        model=str(settings.embedding_model),
        dimension=settings.embedding_dimension,
        timeout_seconds=settings.model_timeout_seconds,
    )


def judge_model_from_settings(settings: Settings) -> LanguageModel | None:
    if not settings.judge_model:
        return None
    return OpenAICompatibleLanguageModel(
        base_url=str(settings.judge_base_url),
        api_key=settings.judge_api_key.get_secret_value() if settings.judge_api_key else "",
        model=settings.judge_model,
        timeout_seconds=settings.model_timeout_seconds,
        max_output_tokens=settings.model_max_output_tokens,
        temperature=0,
    )
