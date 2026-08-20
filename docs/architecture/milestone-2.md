# Milestone 2 architecture: Knowledge + RAG

## Pipeline

```text
Markdown/text
  -> normalize + section parse
  -> token-aware chunking with overlap
  -> configurable EmbeddingProvider
  -> permission-scoped KnowledgeRepository
  -> semantic + lexical candidates
  -> score normalization + merge + rerank
  -> contradiction detection
  -> EvidencePacket + application-owned Citation records
  -> untrusted evidence prompt layer
  -> grounded response + evidence drawer
```

## Source integrity

Knowledge items preserve tenant, user, source system, source ID, title, URL, source timestamps, authority, sensitivity, ingestion time, and metadata. Re-ingesting a changed source creates a new item and marks the previous version superseded; it does not silently replace historical content.

## Retrieval policy

- Tenant and user filters are mandatory.
- Active knowledge only is searched by default.
- Semantic and lexical retrieval run independently and are merged deterministically.
- Authority and freshness affect reranking but cannot manufacture relevance.
- `NO_EVIDENCE_FOUND` means the connected index returned no accessible evidence; it never means evidence does not exist elsewhere.
- Contradictions are returned alongside supporting evidence.

## Risky assumptions and limitations

- The deterministic embedding provider is for development and eval reproducibility, not production relevance quality.
- PostgreSQL/pgvector and full-text execution cannot be exercised in this environment because Docker is unavailable; SQL generation and migrations are tested against SQLite.
- Heuristic contradiction detection catches explicit polarity/state conflicts and will miss nuanced disagreements.
- User/tenant IDs remain development identities rather than authenticated claims. Enterprise ingestion must wait for real authentication and authorization.
- Markdown and plain text are the only parsers in this milestone.
- Model-generated citation syntax is not trusted; user-visible citations are emitted from the evidence packet maintained by application code.
- The current PostgreSQL migration fixes vectors at 128 dimensions to match the deterministic provider. Changing providers or dimensions requires an explicit schema migration and re-embedding job; configuration alone must not silently mix vector spaces.
- The repository owns persistence and database indexing in this milestone rather than adding a pass-through `Indexer` service. Reranking remains deterministic and inspectable inside the retrieval service until a second implementation justifies another abstraction.
