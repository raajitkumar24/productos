# ProductOS documentation

Start with the [root README](../README.md) for setup and the [complete specification](../PRODUCTOS_SPEC.md) for product and engineering requirements.

## Architecture decisions

The records in [adr/](adr/) explain the durable decisions behind the application-owned runtime, deterministic workflows, PostgreSQL/pgvector storage, evidence-first retrieval, MCP boundaries, management safeguards, proactive scheduling, production providers, OIDC tenancy, and measured evaluations.

## Milestone implementation notes

The files in [architecture/](architecture/) document the implementation and verification boundary for milestones 0 through 6:

- Foundation and streaming runtime
- Persistent memory and context
- Knowledge ingestion and evidence-first RAG
- Read-only Atlassian MCP tooling
- Product intelligence workflows
- Evidence-backed management intelligence
- Proactive product leadership

## Operations

- [Production authentication](security/production-authentication.md)
- [Representative-data evaluations](evaluations/representative-data-operations.md)
- [Proactive scheduler](operations/proactive-scheduler.md)

Deployment files under [`deploy/`](../deploy/) are reference manifests. They require environment-specific security, availability, retention, and monitoring review before production use.
