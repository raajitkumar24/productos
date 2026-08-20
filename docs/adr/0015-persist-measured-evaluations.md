# ADR 0015: Persist measured evaluations separately from catalog validation

## Status

Accepted.

## Decision

Synthetic catalog checks remain regression-definition validation. Quality pass rates are persisted only after a configured subject model and judge model execute an operator-supplied, versioned dataset. Runs retain actual outputs, structured rationale, versions, errors, and interpretation limitations without hidden chain-of-thought.

## Consequences

The dashboard cannot accidentally present catalog counts as quality. Representative-data governance, judge calibration, and dataset coverage remain operational responsibilities.
