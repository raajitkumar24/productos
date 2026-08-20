from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from productos.api import create_app
from productos.config import Settings

EVAL_PATH = Path(__file__).parents[1] / "evals" / "retrieval" / "milestone_2.yaml"
EVAL_CASES = yaml.safe_load(EVAL_PATH.read_text())["cases"]


@pytest.mark.parametrize("case", EVAL_CASES, ids=[case["id"] for case in EVAL_CASES])
def test_deterministic_hybrid_retrieval_eval(case: dict[str, str]) -> None:
    app = create_app(
        Settings(database_url="sqlite+aiosqlite:///:memory:", database_auto_create=True)
    )
    with TestClient(app) as client:
        client.post(
            "/v1/knowledge/ingest",
            json={
                "source_type": "eval",
                "source_id": case["id"],
                "title": f"Evidence {case['id']}",
                "content": case["source"],
            },
        )
        client.post(
            "/v1/knowledge/ingest",
            json={
                "source_type": "eval",
                "source_id": f"{case['id']}-distractor",
                "title": "Unrelated office policy",
                "content": "The office kitchen is cleaned every Friday afternoon.",
            },
        )
        response = client.post("/v1/knowledge/search", json={"query": case["query"], "limit": 1})

    packet = response.json()
    assert packet["availability"] == "evidence_found"
    assert packet["evidence"][0]["source_id"] == case["id"]
    assert case["expected"].casefold() in packet["evidence"][0]["content"].casefold()
