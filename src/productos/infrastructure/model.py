import html
import re
from collections.abc import AsyncIterator


class DevelopmentModelCapabilityError(RuntimeError):
    """Raised when deterministic local mode cannot honestly provide a capability."""


class DevelopmentLanguageModel:
    """Transparent local adapter used until a production provider is configured."""

    name = "development"

    async def generate(self, prompt: str) -> str:
        return "".join([chunk async for chunk in self.stream(prompt)])

    async def generate_structured(self, prompt: str, schema: type) -> object:
        raise DevelopmentModelCapabilityError(
            "Structured generation requires a configured production model provider"
        )

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        evidence = re.findall(r'<evidence id="([^"]+)"[^>]*>(.*?)</evidence>', prompt, re.DOTALL)
        if evidence:
            excerpts = [
                f"{html.unescape(content).strip()} [{citation_id}]"
                for citation_id, content in evidence[:3]
            ]
            message = "The indexed evidence states: " + " ".join(excerpts)
            if "contains contradictions" in prompt:
                message += " The indexed sources conflict, so the current state is uncertain."
        elif '<evidence status="none">' in prompt:
            match = re.search(r'<evidence status="none">(.*?)</evidence>', prompt, re.DOTALL)
            detail = html.unescape(match.group(1)).strip() if match else ""
            message = "I could not retrieve sufficient accessible evidence. " + detail
        else:
            message = (
                "ProductOS is running with the deterministic development model. "
                "The application runtime received your request, but no production language "
                "model is configured, so I will not fabricate an answer."
            )
        for token in message.split(" "):
            yield f"{token} "
