from fastapi.testclient import TestClient

from productos.api import create_app
from productos.config import Settings


class WorkflowAtlassianMCP:
    async def call_tool(
        self, provider: str, tool_name: str, arguments: dict[str, object]
    ) -> object:
        if tool_name == "atlassian.list_sites":
            return {
                "sites": [
                    {
                        "cloud_id": "cloud-a",
                        "site_url": "https://a.example.atlassian.net",
                        "site_name": "Product",
                    }
                ]
            }
        if tool_name == "confluence.get_page":
            return {
                "page": {
                    "page_id": "page-1",
                    "title": "Export specification",
                    "content": "- Export audit logs\n- Regional archive restore",
                    "space": "PRODUCT",
                    "cloud_id": "cloud-a",
                }
            }
        if tool_name == "jira.search_issues":
            return {
                "issues": [
                    {
                        "key": "PROD-1",
                        "title": "Export audit logs",
                        "status": "Done",
                        "project": "PROD",
                        "cloud_id": "cloud-a",
                    }
                ]
            }
        return {"results": []}


def _app(mcp: object | None = None):
    return create_app(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            database_auto_create=True,
            atlassian_read_enabled=mcp is not None,
        ),
        mcp_client=mcp,  # type: ignore[arg-type]
    )


def test_workflow_catalog_is_versioned_and_bounded() -> None:
    with TestClient(_app()) as api:
        response = api.get("/v1/workflows")

    workflows = response.json()
    assert response.status_code == 200
    assert {item["name"] for item in workflows} == {
        "deep_research",
        "product_strategy",
        "product_review",
        "spec_execution",
        "experiment_design",
        "decision_memo",
    }
    assert all(item["version"] == "1.0.0" and item["max_iterations"] == 3 for item in workflows)


def test_research_creates_cited_draft_artifact_and_links_work_session() -> None:
    with TestClient(_app()) as api:
        api.post(
            "/v1/knowledge/ingest",
            json={
                "source_type": "customer_research",
                "source_id": "research-1",
                "title": "Admin interviews",
                "content": (
                    "Customer interviews show audit export is painful. "
                    "The primary metric is successful export completion."
                ),
            },
        )
        session = api.post(
            "/v1/work",
            json={
                "title": "Audit export research",
                "objective": "Should we improve audit export?",
                "workflow_type": "deep_research",
            },
        ).json()
        response = api.post(
            "/v1/workflows/execute",
            json={
                "workflow": "deep_research",
                "objective": "Should we improve audit export?",
                "working_session_id": session["id"],
            },
        )
        body = response.json()
        trace = api.get(f"/v1/runs/{body['execution']['run_id']}/traces").json()["events"]
        linked = api.get(f"/v1/work/{session['id']}").json()

    assert response.status_code == 201
    assert body["artifact"]["status"] == "draft"
    assert "[E1]" in body["artifact"]["rendered_content"]
    assert body["artifact"]["id"] in linked["artifact_ids"]
    assert "artifact.created" in [item["event_type"] for item in trace]
    assert [item["event_type"] for item in trace].count("workflow.stage_started") == 11


def test_prd_review_surfaces_document_gaps_without_claiming_product_failure() -> None:
    with TestClient(_app()) as api:
        response = api.post(
            "/v1/workflows/execute",
            json={
                "workflow": "product_review",
                "objective": "Review the assistant PRD",
                "title": "Assistant PRD",
                "source_text": (
                    "# Problem\nCustomers need faster answers.\n"
                    "# Requirements\nThe AI agent must answer using tools."
                ),
            },
        )

    data = response.json()["artifact"]["structured_data"]
    findings = {item["rubric_item"]: item for item in data["findings"]}
    assert findings["success metrics"]["severity"] == "major"
    assert findings["prompt injection"]["severity"] == "question"
    assert "does not prove product quality" in data["limitations"][0]


def test_strategy_with_no_evidence_refuses_premature_commitment() -> None:
    with TestClient(_app()) as api:
        response = api.post(
            "/v1/workflows/execute",
            json={"workflow": "product_strategy", "objective": "Build autonomous pricing"},
        )

    artifact = response.json()["artifact"]
    assert artifact["structured_data"]["recommendation"].startswith("Do not commit")
    assert artifact["structured_data"]["confidence"] == "unknown"


def test_decision_memo_remains_draft_and_does_not_create_decision_memory() -> None:
    with TestClient(_app()) as api:
        response = api.post(
            "/v1/workflows/execute",
            json={
                "workflow": "decision_memo",
                "objective": "Choose an audit export approach",
                "context": {"proposed_decision": "Run a limited pilot"},
            },
        )
        decisions = api.get("/v1/decisions").json()

    artifact = response.json()["artifact"]
    assert artifact["status"] == "draft"
    assert artifact["structured_data"]["memory_promotion"] == "requires_explicit_approval"
    assert decisions == []


def test_experiment_design_preserves_unknown_measurement_as_explicit_gap() -> None:
    with TestClient(_app()) as api:
        response = api.post(
            "/v1/workflows/execute",
            json={"workflow": "experiment_design", "objective": "Test a new AI summary"},
        )

    data = response.json()["artifact"]["structured_data"]
    assert data["primary_metric"].startswith("Not specified")
    assert "model_version" in data["agent_configuration"]
    assert "Selection bias" in data["risks"]


def test_spec_execution_artifact_preserves_no_evidence_as_unknown() -> None:
    with TestClient(_app(WorkflowAtlassianMCP())) as api:
        response = api.post(
            "/v1/workflows/execute",
            json={
                "workflow": "spec_execution",
                "objective": "Compare export spec with delivery",
                "page_id": "page-1",
                "workspace_id": "cloud-a",
                "projects": ["PROD"],
            },
        )

    requirements = response.json()["artifact"]["structured_data"]["requirements"]
    coverage = {item["requirement"]: item for item in requirements}
    assert coverage["Export audit logs"]["status"] == "implemented"
    assert coverage["Regional archive restore"]["status"] == "no_evidence"
    assert "unknown" in coverage["Regional archive restore"]["explanation"]


def test_artifact_reads_are_user_and_tenant_scoped() -> None:
    with TestClient(_app()) as api:
        created = api.post(
            "/v1/workflows/execute",
            json={"workflow": "decision_memo", "objective": "Scoped decision"},
        ).json()["artifact"]
        visible = api.get("/v1/artifacts").json()
        hidden = api.get(
            f"/v1/artifacts/{created['id']}?user_id=00000000-0000-4000-8000-000000000099"
        )

    assert [item["id"] for item in visible] == [created["id"]]
    assert hidden.status_code == 404


def test_workflow_input_contract_requires_document_or_page() -> None:
    with TestClient(_app()) as api:
        review = api.post(
            "/v1/workflows/execute",
            json={"workflow": "product_review", "objective": "Review it"},
        )
        comparison = api.post(
            "/v1/workflows/execute",
            json={"workflow": "spec_execution", "objective": "Compare it"},
        )

    assert review.status_code == 422
    assert comparison.status_code == 422
