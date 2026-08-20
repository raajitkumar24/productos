import hashlib
from uuid import UUID

from productos.application.ports import EmbeddingProvider
from productos.application.repositories import KnowledgeRepository
from productos.domain.knowledge import (
    KnowledgeIngestRequest,
    KnowledgeIngestResult,
    KnowledgeItem,
)
from productos.knowledge.chunking import SectionChunker
from productos.knowledge.parsing import MarkdownTextParser


class KnowledgeIngestionService:
    def __init__(
        self,
        repository: KnowledgeRepository,
        parser: MarkdownTextParser,
        chunker: SectionChunker,
        embeddings: EmbeddingProvider,
    ) -> None:
        self._repository = repository
        self._parser = parser
        self._chunker = chunker
        self._embeddings = embeddings

    async def ingest(
        self, request: KnowledgeIngestRequest, tenant_id: UUID, user_id: UUID
    ) -> KnowledgeIngestResult:
        normalized_content = request.content.replace("\r\n", "\n").replace("\r", "\n").strip()
        checksum = hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()
        existing = await self._repository.active_source(
            tenant_id, user_id, request.source_type, request.source_id
        )
        if existing is not None and existing.content_checksum == checksum:
            return KnowledgeIngestResult(item=existing, chunk_count=0, outcome="unchanged")

        item = KnowledgeItem(
            tenant_id=tenant_id,
            user_id=user_id,
            source_type=request.source_type,
            source_id=request.source_id,
            title=request.title,
            content=normalized_content,
            content_checksum=checksum,
            document_format=request.document_format,
            summary=request.summary,
            author=request.author,
            owner=request.owner,
            workspace=request.workspace,
            project=request.project,
            url=request.url,
            source_created_at=request.source_created_at,
            source_updated_at=request.source_updated_at,
            authority_score=request.authority_score,
            sensitivity=request.sensitivity,
            access_boundary=request.access_boundary,
            supersedes_id=existing.id if existing else None,
            embedding_provider=self._embeddings.name,
            embedding_dimension=self._embeddings.dimension,
            metadata=request.metadata,
        )
        sections = self._parser.parse(normalized_content, request.document_format)
        chunks = self._chunker.chunk(item, sections)
        vectors = await self._embeddings.embed_batch([chunk.content for chunk in chunks])
        for chunk, vector in zip(chunks, vectors, strict=True):
            chunk.embedding = vector
            chunk.metadata["embedding_provider"] = self._embeddings.name
        await self._repository.create(
            item,
            chunks,
            superseded_item_id=existing.id if existing else None,
        )
        return KnowledgeIngestResult(
            item=item,
            chunk_count=len(chunks),
            outcome="superseded" if existing else "created",
        )
