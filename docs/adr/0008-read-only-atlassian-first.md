# ADR 0008: Read-only Atlassian first

- Status: Accepted
- Date: 2026-08-20

## Decision

Milestone 3 registers only Jira, Confluence, and cross-product read capabilities. ProductOS resolves the accessible site before calls and refuses ambiguous multi-site selection. Model text is parsed into structured Jira/Confluence search intents; application code validates identifiers and generates bounded JQL/CQL.

Create, update, comment, publish, transition, and delete capabilities are deliberately absent. Later write support must add exact-payload approval and post-write verification.

## Consequences

- Read operations may run autonomously within declared permissions.
- A connected MCP server exposing write methods does not make those methods available to ProductOS.
- Live integration can be evaluated safely before any external mutation path exists.
