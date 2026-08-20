from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from productos.api import create_app
from productos.config import Settings

CATALOG = Path("evals/proactive/milestone_6.yaml")


def test_proactive_eval_catalog_has_thirty_distinct_cases() -> None:
    suite = yaml.safe_load(CATALOG.read_text())
    cases = suite["cases"]

    assert suite["critical_metric"] == "proactive_noise_rate"
    assert suite["minimum_cases"] == 30
    assert len(cases) == 30
    assert len({case["id"] for case in cases}) == 30
    assert {case["category"] for case in cases} >= {
        "materiality",
        "confidence",
        "actionability",
        "novelty",
        "preferences",
        "scheduler",
        "briefs",
        "decisions",
        "safety",
        "observability",
    }


def test_proactive_catalog_covers_anti_spam_and_constitutional_failures() -> None:
    suite = yaml.safe_load(CATALOG.read_text())
    expected = {case["expected"] for case in suite["cases"]}

    assert "suppress_notification" in expected
    assert "deduplicate_notification" in expected
    assert "suppress_excess_notification" in expected
    assert "no_fabricated_updates" in expected
    assert "no_external_delivery" in expected
    assert "no_performance_notification" in expected
    assert "traceable_run" in expected


def test_evaluation_dashboard_is_truthful_about_unpersisted_quality_results() -> None:
    application = create_app(
        Settings(database_url="sqlite+aiosqlite:///:memory:", database_auto_create=True)
    )
    with TestClient(application) as api:
        response = api.get("/v1/evaluations/catalogs")

    assert response.status_code == 200
    assert response.json()["total_cases"] == 207
    assert response.json()["quality_results_available"] is False
    assert response.json()["catalogs"][-1]["primary_metric"] == "proactive noise rate"
    assert "does not report" in response.json()["limitation"]
