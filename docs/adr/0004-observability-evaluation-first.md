# ADR 0004: Observability and evaluation-first development

- Status: Accepted
- Date: 2026-08-20

## Context

Every ProductOS capability must be observable and evaluatable, especially evidence and management behavior.

## Decision

Emit versioned structured trace events from the first runtime slice. Add capability-specific golden and adversarial evals with each milestone; do not use a single opaque quality score.

## Consequences

New behavior carries trace and eval work. Failures are diagnosable, and regressions can be attributed to runtime, workflow, prompt, model, or retrieval versions.
