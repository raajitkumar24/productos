# ADR 0014: Bind ProductOS tenancy to verified OIDC claims

## Status

Accepted.

## Decision

Production API requests require RS256 OIDC access tokens. User and tenant UUIDs come from verified claims; query and body identifiers may only match those claims. Scheduler and evaluator writes additionally require narrow workload scopes. Browser login uses Authorization Code with PKCE.

## Consequences

Caller-controlled identifiers cannot cross tenant boundaries. Identity-provider claim mapping and workload-token issuance become explicit deployment responsibilities.
