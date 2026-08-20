# ADR 0012: Use an observable application-owned proactive scheduler

## Status

Accepted for Milestone 6.

## Context

ProductOS needs daily and weekly briefs, decision reminders, risk scans, and change notifications without creating opaque autonomous behavior or notification spam. In-process polling in every API replica would make ownership, retries, and duplicate delivery difficult to inspect.

## Decision

Persist schedules, preferences, semantic change snapshots, and deduplicated in-app notifications in the ProductOS database. Expose a deterministic, tenant/user-scoped scheduler tick through the application API and let deployment-owned cron invoke it. Record every scheduler tick and generated artifact through the existing run and trace model. Require novelty, materiality, sufficient confidence, actionability, and user preference gates before notification persistence.

## Consequences

- Scheduler behavior is restart-safe, reproducible, and testable.
- Multiple API replicas do not independently start hidden polling loops.
- Deployment configuration must invoke the scheduler endpoint.
- V1 has no external delivery channel; adding one requires a separate approval-aware write contract.
