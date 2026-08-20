# ADR 0006: Evidence-first hybrid retrieval

- Status: Accepted
- Date: 2026-08-20

## Context

ProductOS must answer over internal product documents with faithful citations, preserve contradictory sources, respect access boundaries, and avoid introducing a separate search service before PostgreSQL is insufficient.

## Decision

Use PostgreSQL full-text search and pgvector behind a provider-independent `KnowledgeRepository`. Every query is scoped by tenant and user before ranking. Hybrid retrieval merges lexical and semantic candidates, then reranks with source authority, freshness, and section/title relevance.

SQLite uses application-side cosine and lexical scoring for local development and deterministic tests only. The development embedding provider is a stable hashed token vector whose dimension comes from configuration. It proves contracts and retrieval behavior but is not represented as production-quality semantics.

Evidence packets and citations are built in application code from persisted knowledge item and chunk identifiers. Retrieved content is wrapped as untrusted data and cannot alter system or permission instructions. Conflicting evidence remains visible.

## Consequences

- PostgreSQL remains the only production data and retrieval service through Milestone 2.
- Permission filters are applied before similarity scoring, preventing cross-tenant vector leakage.
- Citation identifiers cannot be invented by a model.
- SQLite and deterministic embeddings provide reproducible tests but cannot validate PostgreSQL query plans or production recall.
- Embedding-provider changes require explicit re-embedding and version tracking.
