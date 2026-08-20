# ADR 0009: Store artifacts as structured data plus rendered Markdown

Status: Accepted

## Context

Product Intelligence workflows need outputs that are readable by leaders, inspectable by evaluators, and stable across presentation changes. Storing only prose makes evaluation and downstream reuse brittle; storing only JSON produces a poor working artifact.

## Decision

Persist both typed structured data and application-rendered Markdown on every artifact. Store the workflow, workflow version, run, source references, model metadata, status, and optional working session link. Artifacts are drafts by default. A draft decision memo does not become accepted decision memory without explicit authorization through the decision boundary.

## Consequences

Evaluations can inspect exact fields while users receive a coherent memo. Rendering is deterministic and version-attributable. Schema evolution and re-rendering require explicit migration/version policies in later milestones.
