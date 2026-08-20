import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from productos.api import create_app
from productos.application.ports import MCPClientError
from productos.atlassian import AtlassianReadProvider
from productos.atlassian.query import build_jql
from productos.config import Settings
from productos.domain.atlassian import JiraSearchIntent
from productos.domain.tools import PermissionContext, ToolCallStatus, ToolErrorCode
from productos.infrastructure.tracing import InMemoryTraceRepository
from productos.mcp.client import StreamableHTTPMCPClient
from productos.tools import PermissionEngine, ToolExecutor, atlassian_tool_registry


class FakeAtlassianMCP:
    def __init__(self, multiple_sites: bool = False, fail_jira: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.multiple_sites = multiple_sites
        self.fail_jira = fail_jira

    async def call_tool(
        self, provider: str, tool_name: str, arguments: dict[str, object]
    ) -> object:
        self.calls.append((tool_name, arguments))
        if tool_name == "atlassian.list_sites":
            sites = [
                {
                    "cloud_id": "cloud-a",
                    "site_url": "https://a.example.atlassian.net",
                    "site_name": "Product A",
                    "user_identity": "user-1",
                    "accessible_projects": ["PROD"],
                    "accessible_spaces": ["PRODUCT"],
                }
            ]
            if self.multiple_sites:
                sites.append(
                    {
                        "cloud_id": "cloud-b",
                        "site_url": "https://b.example.atlassian.net",
                        "site_name": "Product B",
                    }
                )
            return {"sites": sites}
        if tool_name == "jira.search_issues":
            if self.fail_jira:
                raise MCPClientError(ToolErrorCode.UPSTREAM_ERROR, "Jira is unavailable.")
            return {
                "issues": [
                    {
                        "key": "PROD-101",
                        "title": "Export audit logs",
                        "description": "Enterprise admins can export audit logs.",
                        "issue_type": "Story",
                        "status": "Done",
                        "assignee": "Asha",
                        "project": "PROD",
                        "updated_at": "2026-08-19T10:00:00Z",
                        "url": "https://a.example.atlassian.net/browse/PROD-101",
                        "cloud_id": "cloud-a",
                    },
                    {
                        "key": "PROD-102",
                        "title": "Admin retention status view",
                        "description": "Show retention status to admins.",
                        "issue_type": "Story",
                        "status": "In Progress",
                        "assignee": "Dev",
                        "project": "PROD",
                        "updated_at": "2026-08-20T08:00:00Z",
                        "url": "https://a.example.atlassian.net/browse/PROD-102",
                        "cloud_id": "cloud-a",
                    },
                ]
            }
        if tool_name == "confluence.search":
            return {
                "pages": [
                    {
                        "page_id": "page-7",
                        "title": "Audit administration spec",
                        "content": "The current product plan covers audit export and retention.",
                        "space": "PRODUCT",
                        "version": 4,
                        "updated_at": "2026-08-18T12:00:00Z",
                        "url": "https://a.example.atlassian.net/wiki/page-7",
                        "cloud_id": "cloud-a",
                    }
                ]
            }
        if tool_name == "confluence.get_page":
            return {
                "page": {
                    "page_id": "page-7",
                    "title": "Audit administration spec",
                    "content": (
                        "# Requirements\n"
                        "- User can export audit logs\n"
                        "- Admin sees retention status\n"
                        "- Support regional archive restore"
                    ),
                    "space": "PRODUCT",
                    "version": 4,
                    "url": "https://a.example.atlassian.net/wiki/page-7",
                    "cloud_id": "cloud-a",
                }
            }
        return {"results": []}


def _app(client: object, **settings: object):
    return create_app(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            database_auto_create=True,
            atlassian_read_enabled=True,
            **settings,
        ),
        mcp_client=client,  # type: ignore[arg-type]
    )


def _events(text: str) -> list[tuple[str, dict[str, object]]]:
    result = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        result.append(
            (
                lines[0].removeprefix("event: "),
                json.loads(lines[1].removeprefix("data: ")),
            )
        )
    return result


def test_registry_exposes_only_declared_read_tools() -> None:
    definitions = atlassian_tool_registry().list()

    assert len(definitions) == 13
    assert all(tool.read_only and not tool.requires_confirmation for tool in definitions)
    assert all(tool.required_permissions == {"atlassian:read"} for tool in definitions)
    assert not any("create" in tool.name or "update" in tool.name for tool in definitions)
    search = next(tool for tool in definitions if tool.name == "jira.search_issues")
    assert search.input_schema["required"] == ["cloud_id", "intent"]


@pytest.mark.asyncio
async def test_official_mcp_transport_returns_only_structured_content(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class FakeSDKClient:
        def __init__(self, url: str) -> None:
            assert url == "https://mcp.example.test"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def call_tool(self, name: str, arguments: dict[str, object]) -> object:
            calls.append((name, arguments))
            return SimpleNamespace(
                is_error=False,
                structured_content={"sites": []},
                content=[{"untrusted": "ignored"}],
            )

    monkeypatch.setattr("productos.mcp.client.Client", FakeSDKClient)
    client = StreamableHTTPMCPClient("https://mcp.example.test")

    result = await client.call_tool("atlassian", "atlassian.list_sites", {})

    assert result == {"sites": []}
    assert calls == [("atlassian.list_sites", {})]


@pytest.mark.asyncio
async def test_permission_denial_happens_before_mcp_transport() -> None:
    client = FakeAtlassianMCP()
    registry = atlassian_tool_registry()
    executor = ToolExecutor(
        registry,
        {"atlassian": AtlassianReadProvider(client)},
        PermissionEngine(),
        InMemoryTraceRepository(),
        None,
        "1.0.0",
        "1.0.0",
        5,
        0,
        2,
    )
    context = PermissionContext(tenant_id=uuid4(), user_id=uuid4())

    result = await executor.execute(uuid4(), "atlassian.list_sites", {}, context)

    assert result.status == ToolCallStatus.FAILED
    assert result.error_code == ToolErrorCode.AUTHORIZATION_FAILED
    assert client.calls == []


@pytest.mark.asyncio
async def test_tool_contract_and_iteration_budget_fail_before_transport() -> None:
    client = FakeAtlassianMCP()
    executor = ToolExecutor(
        atlassian_tool_registry(),
        {"atlassian": AtlassianReadProvider(client)},
        PermissionEngine(),
        InMemoryTraceRepository(),
        None,
        "1.0.0",
        "1.0.0",
        5,
        0,
        2,
        max_iterations=2,
    )
    context = PermissionContext(tenant_id=uuid4(), user_id=uuid4(), permissions={"atlassian:read"})

    invalid = await executor.execute(uuid4(), "jira.get_issue", {}, context)
    over_budget = await executor.execute(uuid4(), "atlassian.list_sites", {}, context, iteration=3)

    assert invalid.error_code == ToolErrorCode.INVALID_ARGUMENT
    assert over_budget.error_code == ToolErrorCode.BUDGET_EXCEEDED
    assert client.calls == []


def test_structured_jql_escapes_text_and_rejects_project_syntax() -> None:
    query = build_jql(JiraSearchIntent(projects=["PROD"], text=['alpha" OR project=SECRET']))

    assert 'text ~ "alpha\\" OR project=SECRET"' in query
    with pytest.raises(ValueError):
        JiraSearchIntent(projects=["PROD) OR project=SECRET"])


def test_multi_site_resolution_requires_explicit_site() -> None:
    client = FakeAtlassianMCP(multiple_sites=True)
    with TestClient(_app(client)) as api:
        response = api.post(
            "/v1/organization/current-state", json={"topic": "audit administration"}
        )

    state = response.json()["current_state"]
    assert any("select a site explicitly" in item for item in state["unknowns"])
    assert not any(call[0] == "jira.search_issues" for call in client.calls)


def test_current_state_combines_confluence_jira_and_indexed_evidence() -> None:
    client = FakeAtlassianMCP()
    with TestClient(_app(client)) as api:
        api.post(
            "/v1/knowledge/ingest",
            json={
                "source_type": "decision",
                "source_id": "audit-decision",
                "title": "Audit decision",
                "content": "Audit export is required for the enterprise launch.",
            },
        )
        response = api.post(
            "/v1/organization/current-state",
            json={"topic": "current state of audit administration", "cloud_id": "cloud-a"},
        )

    body = response.json()
    assert response.status_code == 200
    assert body["current_state"]["implementation_status"] == "Done, In Progress"
    assert body["evidence"]["source_coverage"] == {
        "decision": 1,
        "confluence_page": 1,
        "jira_issue": 2,
    }
    assert {item["source_id"] for item in body["evidence"]["evidence"]} >= {
        "page-7",
        "PROD-101",
    }


def test_organization_search_returns_normalized_cross_system_evidence() -> None:
    with TestClient(_app(FakeAtlassianMCP())) as api:
        response = api.post(
            "/v1/organization/search",
            json={"topic": "audit administration", "cloud_id": "cloud-a"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["availability"] == "evidence_found"
    assert body["source_coverage"] == {"confluence_page": 1, "jira_issue": 2}


def test_chat_streams_live_tool_summary_and_cited_atlassian_evidence() -> None:
    with TestClient(_app(FakeAtlassianMCP())) as api:
        response = api.post(
            "/v1/chat",
            json={
                "message": "What is the current state of audit administration?",
                "workspace_id": "cloud-a",
            },
        )
        events = _events(response.text)
        run_id = events[0][1]["run_id"]
        traces = api.get(f"/v1/runs/{run_id}/traces").json()["events"]

    tool = next(data for event, data in events if event == "tool")
    evidence = next(data for event, data in events if event == "evidence")
    answer = "".join(str(data["text"]) for event, data in events if event == "delta")
    assert len(tool["calls"]) == 2  # type: ignore[arg-type]
    assert evidence["source_coverage"]["jira_issue"] == 2  # type: ignore[index]
    assert "[E1]" in answer
    trace_types = [item["event_type"] for item in traces]
    assert "tool.permission_checked" in trace_types
    assert "tool.call_completed" in trace_types


def test_spec_execution_preserves_no_evidence_as_unknown() -> None:
    with TestClient(_app(FakeAtlassianMCP())) as api:
        response = api.post(
            "/v1/organization/compare-spec-execution",
            json={"page_id": "page-7", "cloud_id": "cloud-a", "projects": ["PROD"]},
        )

    coverage = {item["requirement"]: item for item in response.json()["requirements"]}
    assert coverage["User can export audit logs"]["status"] == "implemented"
    assert coverage["Admin sees retention status"]["status"] == "in_progress"
    missing = coverage["Support regional archive restore"]
    assert missing["status"] == "no_evidence"
    assert "unknown" in missing["explanation"]


def test_jira_failure_is_reported_without_fabricated_execution_state() -> None:
    with TestClient(_app(FakeAtlassianMCP(fail_jira=True), max_tool_retries=0)) as api:
        response = api.post(
            "/v1/organization/current-state",
            json={"topic": "current state of audit administration", "cloud_id": "cloud-a"},
        )

    state = response.json()["current_state"]
    assert state["implementation_status"] is None
    assert "Jira is unavailable." in state["unknowns"]
    assert state["product_status"] == "Audit administration spec"
