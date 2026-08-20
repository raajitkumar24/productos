# ADR 0002: Workflows over multi-agent orchestration

- Status: Accepted
- Date: 2026-08-20

## Context

The core product tasks are structured and require consistent evidence, permission, and evaluation behavior.

## Decision

Use one core runtime with versioned deterministic workflows. Do not introduce a multi-agent swarm unless measured requirements later show workflows are insufficient.

## Consequences

Tracing and eval attribution are simpler, while workflow branching must be modeled explicitly.
