# ADR 0010: Evidence-backed management intelligence

Status: Accepted

## Context

Management briefs can materially affect people and priorities. Product activity, missing records, and temporal correlation are insufficient evidence for product quality, causal attribution, or PM performance.

## Decision

ProductOS produces management signals from application-scoped initiative, outcome, commitment, decision, and artifact records. Every signal carries an epistemic label, evidence references, confidence, time window, limitations, and an inspectable correction history. Initiative health is eight categorical dimensions without an aggregate score. Recurring coaching patterns require at least three distinct initiatives; they remain interpretations and explicitly require manager context. Positive evidence is surfaced alongside risks.

Management workflows are deterministic, versioned paths on the existing application-owned runtime. Their artifacts and trace events remain inspectable. Missing or inaccessible evidence produces `unknown` or a documentation-gap limitation, never an employee conclusion.

## Consequences

The system is conservative and may miss real patterns when records are sparse. That is preferable to unsupported management claims. Future probabilistic detection must retain these evidence contracts and be evaluated against false management signal rate before release.
