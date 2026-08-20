# Milestone 3 architecture: MCP + Atlassian

```text
request
  -> deterministic organizational intent routing
  -> live/index freshness planner
  -> CapabilityResolver
  -> PermissionEngine
  -> ToolExecutor (budget, timeout, dedupe, trace)
  -> MCPClient transport
  -> Atlassian adapter normalization
  -> JiraIssue / ConfluencePage
  -> EvidencePacket / current state / spec-execution comparison
```

## Boundaries

- ProductOS registers read-only Atlassian tools; transport-advertised write tools are invisible.
- Site selection is explicit when more than one site is accessible.
- JQL/CQL is generated only from validated structured intent.
- Raw MCP responses are untrusted and normalized before use.
- Tool-call persistence contains fingerprints, counts, status, latency, versions, and error codes—not credentials or raw provider payloads.
- `NO_EVIDENCE` in spec comparison never becomes `NOT_IMPLEMENTED`.

## Transport and development limitation

The default local MCP client is intentionally unavailable. When a deployment configures a Streamable HTTP endpoint, ProductOS uses the official MCP Python SDK behind the application-owned `MCPClient` port. Authentication remains outside ProductOS in an approved gateway or sidecar. Deterministic mocked transports exercise the complete flow in tests without claiming access to company Jira or Confluence.
