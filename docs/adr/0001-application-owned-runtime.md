# ADR 0001: Application-owned agent runtime

- Status: Accepted
- Date: 2026-08-20

## Context

ProductOS needs inspectable execution, deterministic permission checks, bounded tool use, and reliable tracing.

## Decision

Application code owns typed run state and transitions. Models may produce content or proposed actions but never grant themselves execution authority.

## Consequences

Workflows remain testable without a model. Runtime evolution requires explicit state/version migrations, but control and auditability stay inside ProductOS.
