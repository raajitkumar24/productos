import re

from productos.domain.knowledge import KnowledgeChunk, KnowledgeItem, ParsedSection


class SectionChunker:
    def __init__(self, max_tokens: int = 500, overlap_tokens: int = 60) -> None:
        if max_tokens < 20:
            raise ValueError("max_tokens must be at least 20")
        if overlap_tokens < 0 or overlap_tokens >= max_tokens:
            raise ValueError("overlap_tokens must be non-negative and smaller than max_tokens")
        self._max_tokens = max_tokens
        self._overlap_tokens = overlap_tokens

    def chunk(self, item: KnowledgeItem, sections: list[ParsedSection]) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        for section in sections:
            tokens = re.findall(r"\S+", section.content)
            if not tokens:
                continue
            start = 0
            while start < len(tokens):
                window = tokens[start : start + self._max_tokens]
                chunks.append(
                    KnowledgeChunk(
                        knowledge_item_id=item.id,
                        tenant_id=item.tenant_id,
                        user_id=item.user_id,
                        chunk_index=len(chunks),
                        content=" ".join(window),
                        token_count=len(window),
                        embedding=[],
                        section_title=section.title,
                        parent_section=section.parent_title,
                    )
                )
                if start + self._max_tokens >= len(tokens):
                    break
                start += self._max_tokens - self._overlap_tokens
        return chunks
