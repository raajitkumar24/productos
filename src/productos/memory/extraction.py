import re
from uuid import UUID

from productos.domain.memory import MemoryCandidate, MemoryType, ProvenanceType


class ExplicitMemoryExtractor:
    """Conservative extractor for statements that explicitly ask to be remembered."""

    _preference_patterns = (
        re.compile(r"^\s*I prefer\s+(.+?)(?:[.!?]|$)", re.IGNORECASE),
        re.compile(r"^\s*my preference is\s+(.+?)(?:[.!?]|$)", re.IGNORECASE),
    )
    _remember_pattern = re.compile(
        r"^\s*(?:please\s+)?remember that\s+(.+?)(?:[.!?]|$)", re.IGNORECASE
    )

    def extract(self, user_id: UUID, text: str, source_id: str) -> list[MemoryCandidate]:
        candidates: list[MemoryCandidate] = []
        seen: set[str] = set()
        for pattern in self._preference_patterns:
            for match in pattern.finditer(text):
                preference = match.group(1).strip()
                normalized = preference.casefold()
                if normalized in seen:
                    continue
                seen.add(normalized)
                candidates.append(
                    MemoryCandidate(
                        user_id=user_id,
                        memory_type=MemoryType.PREFERENCE,
                        content=preference,
                        summary=f"User preference: {preference}",
                        confidence=1.0,
                        importance=0.75,
                        source_type="conversation_message",
                        source_id=source_id,
                        provenance_type=ProvenanceType.EXPLICIT_USER,
                        memory_key=self._preference_key(preference),
                    )
                )

        for match in self._remember_pattern.finditer(text):
            statement = match.group(1).strip()
            normalized = statement.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            candidates.append(
                MemoryCandidate(
                    user_id=user_id,
                    memory_type=MemoryType.SEMANTIC,
                    content=statement,
                    summary=statement[:1_000],
                    confidence=1.0,
                    importance=0.75,
                    source_type="conversation_message",
                    source_id=source_id,
                    provenance_type=ProvenanceType.EXPLICIT_USER,
                    memory_key=None,
                )
            )
        return candidates

    @staticmethod
    def _preference_key(preference: str) -> str | None:
        words = set(re.findall(r"[a-z0-9]+", preference.casefold()))
        if words & {"concise", "brief", "short", "detailed", "verbose", "thorough"}:
            return "response_detail"
        if words & {"bullets", "bullet", "prose", "table", "tables", "format"}:
            return "response_format"
        if words & {"formal", "casual", "direct", "friendly", "tone"}:
            return "response_tone"
        if words & {"python", "typescript", "javascript", "fastapi", "nextjs", "react"}:
            return "technology_preference"
        return None
