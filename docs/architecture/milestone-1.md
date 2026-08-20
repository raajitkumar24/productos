# Milestone 1 architecture: Persistent Intelligence

## Scope

Milestone 1 adds conversations, messages, working sessions, memory lifecycle management, preference/belief/decision memory, lexical memory retrieval, and a token-budgeted `ContextPlanner`.

```text
chat request
  -> resolve stable user + conversation
  -> persist user message
  -> retrieve active memories for that user
  -> ContextPlanner ranks and budgets context
  -> model stream
  -> persist assistant message
  -> explicit-memory candidate extraction
  -> MemoryService validates/deduplicates/resolves conflicts
  -> trace memory and context events
```

The answer-generation model never writes memory directly.

## Persistence

SQLAlchemy repositories target PostgreSQL in production. SQLite is supported only for zero-setup local development and isolated tests. Schema changes are represented by Alembic migrations. Tenant authentication is not yet implemented, so connected enterprise data remains out of scope.

## Context ranking

Milestone 1 has no embeddings. The planner uses inspectable lexical relevance, provenance authority, importance, recency, and estimated token cost. Semantic/vector retrieval belongs to Milestone 2.

## Risky assumptions and limitations

- The fixed development user ID is not authentication. Production deployment must reject unauthenticated identity before internal integrations are enabled.
- Deterministic extraction recognizes only explicit preference phrases and deliberately misses ambiguous statements.
- Keyword-based preference keys cover response detail, response format, response tone, and technology preferences. Unclassified preferences do not automatically supersede one another.
- SQLite does not exercise PostgreSQL concurrency or migration behavior; PostgreSQL integration tests require an available service.
- Memory relevance is lexical until embeddings arrive in Milestone 2.
- Decision approval is explicit through its API. Draft decision artifacts from later workflows must not become accepted decision memory automatically.
