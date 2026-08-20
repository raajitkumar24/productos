# Milestone 0 architecture

## Outcome

Milestone 0 establishes the smallest inspectable vertical slice:

```text
Next.js chat workspace
  -> POST /v1/chat (SSE)
  -> application-owned AgentRuntime
  -> provider-independent LanguageModel port
  -> development model adapter
  -> trace repository
```

The runtime, not the model, owns run state and execution authority. The current chat workflow has no tools, retrieval, memory, or external writes.

## Facts

- The supplied ProductOS specification requires Python 3.12+, FastAPI, Next.js, PostgreSQL/pgvector, application-owned orchestration, tracing, and incremental milestones.
- The repository was empty before this milestone.
- No production model credentials or provider selection were supplied.

## Decisions

- Use Server-Sent Events for the first streaming contract because the flow is server-to-client after one POST request.
- Keep traces in memory for the executable vertical slice while defining a repository boundary. PostgreSQL-backed persistence belongs in the next database increment.
- Use a transparent deterministic development model. It explicitly declines to synthesize an answer rather than simulating unavailable model intelligence.

## Risky assumptions and limitations

- In-memory traces disappear on restart and do not support multiple API replicas.
- The development adapter proves orchestration, not answer quality.
- Database lifecycle and migrations are not wired yet; PostgreSQL is provisioned locally to avoid speculative schema work before persistent domain behavior is implemented.
- User identity is request-provided for now. Authentication and tenant authorization must precede connected internal data.
- SSE cancellation and backpressure need production hardening.

## Deferred by design

Memory, RAG, MCP, Atlassian, workflow artifacts, management intelligence, proactive scheduling, employee analysis, and external writes are later milestones.
