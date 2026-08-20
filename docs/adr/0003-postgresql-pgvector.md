# ADR 0003: PostgreSQL and pgvector

- Status: Accepted
- Date: 2026-08-20

## Context

ProductOS needs relational integrity, JSON flexibility, full-text retrieval, vector search, provenance, tenant boundaries, and operational simplicity.

## Decision

Use PostgreSQL as the system of record and pgvector for embeddings. Keep embedding dimensions in provider/configuration boundaries rather than domain logic.

## Consequences

One database supports early milestones. Retrieval tuning and vector migrations require deliberate operational work later.
