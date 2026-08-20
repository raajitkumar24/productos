# ADR 0005: Append-only memory architecture

- Status: Accepted
- Date: 2026-08-20

## Context

ProductOS must retain useful preferences, beliefs, and decisions across conversations without allowing generated answers to silently rewrite history. Provenance, confidence, conflict, and supersession must remain inspectable.

## Decision

Memory writes pass through a dedicated `MemoryService`. The chat model may only provide candidates; validation, normalization, deduplication, conflict policy, persistence, and supersession are application-owned.

Memory content corrections are append-only. A correction creates a new memory and a typed relationship to the preserved prior record. Archival may update status in place because it does not change the historical claim. Explicit user memories outrank inferred memories. A lower-authority contradiction is retained as a candidate and linked, but does not displace the active explicit memory.

Milestone 1 uses conservative deterministic extraction for a small set of explicit phrases. Broad model-based extraction is deferred until it can be evaluated for contamination and false-memory rates.

## Consequences

- History, provenance, and user corrections remain inspectable.
- Retrieval must filter status and follow relationships.
- Duplicate and conflict behavior is deterministic and unit-testable.
- Recall is intentionally lower than an aggressive extractor; this is preferable to silent memory contamination.
