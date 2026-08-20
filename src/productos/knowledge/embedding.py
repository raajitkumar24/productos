import hashlib
import math
import re


class DeterministicEmbeddingProvider:
    """Stable hashed token vectors for development and deterministic evals."""

    name = "deterministic-hash-v1"

    def __init__(self, dimension: int) -> None:
        if dimension < 16:
            raise ValueError("Embedding dimension must be at least 16")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        tokens = re.findall(r"[a-z0-9]+", text.casefold())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude:
            vector = [value / magnitude for value in vector]
        return vector

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_text(text) for text in texts]
