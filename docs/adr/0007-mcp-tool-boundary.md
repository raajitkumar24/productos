# ADR 0007: Application-owned MCP and tool boundary

- Status: Accepted
- Date: 2026-08-20

## Context

ProductOS needs live organizational evidence without allowing provider payloads, model-generated queries, or MCP servers to control execution authority. Tool behavior must remain permission-aware, traceable, budgeted, and provider-independent.

## Decision

The application owns `ToolRegistry`, `CapabilityResolver`, `PermissionEngine`, `ToolExecutor`, structured search intents, output normalization, and persistence of non-secret call metadata. MCP is a transport port. Provider adapters translate ProductOS arguments to MCP calls and normalize results before any evidence or prompt construction.

Tool definitions declare risk, read/write behavior, confirmation, idempotency, timeout, sensitivity, schemas, and required permissions. Equivalent calls are fingerprinted and deduplicated within a run. Raw credentials, tokens, unrestricted JQL/CQL, and raw MCP payloads are never stored in traces or exposed to the model.

## Consequences

- A provider transport can be replaced without changing ProductOS domain objects.
- Tool failures and empty results remain distinguishable.
- Adding a tool requires a visible contract, permission policy, trace path, and eval.
- The default development transport reports unavailable; it never fabricates Atlassian content.
