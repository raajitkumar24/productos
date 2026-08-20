# Milestone 4 architecture: Product Intelligence workflows

```text
workflow request
  -> versioned WorkflowDefinition
  -> application-owned WorkflowRuntime
  -> bounded deterministic stages + traces
  -> indexed / organizational EvidencePacket
  -> deduplicated EvidenceLedger
  -> typed structured analysis
  -> rendered Markdown
  -> draft Artifact + optional WorkingSession link
```

## Implemented workflows

- deep research with questions and eight evidence-coverage dimensions
- product strategy with assumptions, alternatives, reversibility, tradeoffs, and validation
- PRD/product review with base and AI-specific rubrics and calibrated severities
- Confluence spec versus Jira execution coverage
- experiment design including AI configuration fields
- draft decision memo with explicit memory-promotion boundary

## Trust boundaries

- Retrieved and pasted documents remain untrusted evidence; they cannot alter workflow authority.
- Evidence gaps are represented as unknown or no evidence, never as proof of absence or failure.
- Recommendations weaken or defer when critical evidence is missing.
- Artifacts are draft by default and external writes remain absent.
- Stage traces store structured summaries, not private chain-of-thought.

## Development limitation

The development workflow generator is deterministic. It validates orchestration, evidence handling, persistence, rendering, UI, tracing, and eval contracts without claiming production-quality model judgment. A production structured-generation adapter can replace individual synthesis steps behind these application-owned contracts.
