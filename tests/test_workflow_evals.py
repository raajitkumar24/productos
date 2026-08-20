from collections import Counter
from pathlib import Path

import yaml
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
                    }
                ]
            }
        return {"results": []}


def _app(mcp: object):
    return create_app(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            database_auto_create=True,
            atlassian_read_enabled=True,
        ),
        mcp_client=mcp,  # type: ignore[arg-type]
    )


CATALOG = Path("evals/product_intelligence/milestone_4.yaml")


def test_milestone_4_catalog_executes_50_safe_workflow_cases() -> None:
    catalog = yaml.safe_load(CATALOG.read_text())
    cases = catalog["cases"]
    assert len(cases) == 50
    assert len({case["id"] for case in cases}) == 50
    counts = Counter(case["workflow"] for case in cases)
    assert all(counts[name] >= 7 for name in counts)

    with TestClient(_app(WorkflowAtlassianMCP())) as api:
        for case in cases:
            payload: dict[str, object] = {
                "workflow": case["workflow"],
                "objective": case["objective"],
            }
            if case["workflow"] == "product_review":
                payload["source_text"] = (
                    "# Problem\nCustomers need reliable AI answers.\n"
                    "# Requirements\nThe agent must cite evidence."
                )
            if case["workflow"] == "spec_execution":
                payload.update(page_id="page-1", workspace_id="cloud-a", projects=["PROD"])
            response = api.post("/v1/workflows/execute", json=payload)
            assert response.status_code == 201, case["id"]
            artifact = response.json()["artifact"]
            assert artifact["status"] == "draft"
            assert set(case["expected_keys"]).issubset(artifact["structured_data"])
            lowered = artifact["rendered_content"].casefold()
            assert not any(phrase in lowered for phrase in catalog["forbidden_phrases"])


def test_workflow_eval_catalog_declares_specialized_metrics() -> None:
    catalog = yaml.safe_load(CATALOG.read_text())

    assert set(catalog["metrics"]) >= {
        "evidence_coverage",
        "assumption_quality",
        "recommendation_grounding",
        "severity_calibration",
        "experiment_quality",
    }
