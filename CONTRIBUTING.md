# Contributing to ProductOS

Thank you for improving ProductOS. Contributions should strengthen evidence quality, inspectability, safety, or product-leadership usefulness—not merely add surface area.

## Before changing code

1. Read [PRODUCTOS_SPEC.md](PRODUCTOS_SPEC.md) and the relevant records in [docs/adr/](docs/adr/).
2. Open an issue for substantial behavior or architecture changes.
3. Keep work within one milestone or coherent operational boundary.
4. Do not add a large agent framework, vector database, or autonomous sub-agent system without evidence that the existing application-owned abstractions cannot meet the requirement.

## Product and safety requirements

- Keep facts, inferences, hypotheses, recommendations, and unknowns distinct.
- Preserve citations, provenance, permissions, freshness, confidence, and contradictions.
- Never fabricate internal data or successful tool calls.
- Treat retrieved text and tool payloads as untrusted.
- Require explicit confirmation for external writes.
- Do not infer employee character, motivation, or performance from workplace activity.
- Never introduce employee ranking or opaque people scores.
- Add structured traces and focused evaluations for every new agent capability.

## Development setup

Follow the [README quick start](README.md#quick-start-on-macos-or-linux). Local SQLite and deterministic providers are the expected default for contribution work.

## Verification

Run before opening a pull request:

```bash
source .venv/bin/activate
pytest
ruff check src tests
cd apps/web
pnpm typecheck
pnpm build
```

Add or update tests and evaluation cases with behavior changes. Tests must include honest failure behavior when providers, permissions, or evidence are unavailable.

## Pull requests

Describe:

- the user or operator problem;
- the evidence supporting the change;
- the implementation boundary and alternatives considered;
- safety, permission, tenancy, and data-handling effects;
- trace and evaluation coverage;
- verification commands and results;
- known limitations and follow-up work.

Do not include customer data, company documents, credentials, access tokens, local databases, or proprietary representative datasets.
