import json

import httpx
import pytest
from pydantic import BaseModel

from productos.config import Settings
from productos.infrastructure.model import (
    DevelopmentLanguageModel,
    DevelopmentModelCapabilityError,
)
from productos.infrastructure.providers import (
    ModelProviderError,
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleLanguageModel,
    embedding_provider_from_settings,
    language_model_from_settings,
)


class StructuredAnswer(BaseModel):
    answer: str
    confidence: float


@pytest.mark.asyncio
async def test_development_model_fails_structured_generation_transparently() -> None:
    model = DevelopmentLanguageModel()
    with pytest.raises(DevelopmentModelCapabilityError, match="production model provider"):
        await model.generate_structured("question", StructuredAnswer)


@pytest.mark.asyncio
async def test_openai_compatible_model_supports_generate_structured_and_stream() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        if payload.get("stream"):
            return httpx.Response(
                200,
                text=(
                    'data: {"choices":[{"delta":{"content":"Evidence "}}]}\n\n'
                    'data: {"choices":[{"delta":{"content":"first."}}]}\n\n'
                    "data: [DONE]\n\n"
                ),
            )
        if "response_format" in payload:
            content = '{"answer":"Evidence first","confidence":0.9}'
        else:
            content = "Evidence first."
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://models.example/v1"
    )
    model = OpenAICompatibleLanguageModel(
        "https://models.example/v1", "secret", "production-model", client=client
    )

    assert await model.generate("question") == "Evidence first."
    structured = await model.generate_structured("question", StructuredAnswer)
    assert structured == StructuredAnswer(answer="Evidence first", confidence=0.9)
    assert "".join([chunk async for chunk in model.stream("question")]) == "Evidence first."
    await client.aclose()


@pytest.mark.asyncio
async def test_embedding_adapter_preserves_order_and_enforces_dimension() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ]
            },
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://models.example/v1"
    )
    provider = OpenAICompatibleEmbeddingProvider(
        "https://models.example/v1", "secret", "embedding-model", 2, client=client
    )
    assert await provider.embed_batch(["first", "second"]) == [[1.0, 0.0], [0.0, 1.0]]
    await client.aclose()


@pytest.mark.asyncio
async def test_provider_errors_are_safe_and_do_not_expose_response_or_key() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream-secret-detail")

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://models.example/v1"
    )
    model = OpenAICompatibleLanguageModel(
        "https://models.example/v1", "configured-secret", "model", client=client
    )
    with pytest.raises(ModelProviderError) as error:
        await model.generate("question")
    assert "secret" not in str(error.value)
    await client.aclose()


def test_provider_factories_require_explicit_production_configuration() -> None:
    with pytest.raises(ValueError, match="PRODUCTOS_MODEL_BASE_URL"):
        Settings(model_provider="openai_compatible")

    settings = Settings(
        model_provider="openai_compatible",
        model_base_url="https://models.example/v1",
        model_api_key="secret",
        model_name="product-model",
        embedding_provider="openai_compatible",
        embedding_model="embedding-model",
        embedding_dimension=1536,
    )
    assert language_model_from_settings(settings).name.endswith("product-model")
    assert embedding_provider_from_settings(settings).dimension == 1536
    assert "secret" not in repr(settings)
