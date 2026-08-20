# ADR 0013: Use OpenAI-compatible production provider adapters

## Status

Accepted.

## Decision

Production language and embedding calls use small OpenAI-compatible HTTP adapters behind the existing ProductOS interfaces. Domain objects do not import provider SDK types. Provider URLs, models, dimensions, timeouts, and keys are deployment configuration; missing production configuration fails startup. Raw provider bodies and credentials are never surfaced in safe errors.

## Consequences

Compatible managed or self-hosted providers can be selected without changing domain code. Provider-specific features outside the compatible contract require an explicit adapter rather than leaking into workflows.
