from fastapi.testclient import TestClient

from productos.api import create_app
from productos.config import Settings


def _app():
    return create_app(
        Settings(database_url="sqlite+aiosqlite:///:memory:", database_auto_create=True)
    )


def _initiative(api: TestClient, name: str = "Evidence initiative", owner: str = "pm-1"):
    response = api.post(
        "/v1/initiatives",
        json={
            "name": name,
            "problem": "Customers cannot inspect exports.",
            "owner_ids": [owner],
            "jira_issue_ids": ["PROD-42"],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_initiative_health_is_categorical_evidence_backed_and_unscored() -> None:
    with TestClient(_app()) as api:
        item = _initiative(api)
        response = api.get(f"/v1/initiatives/{item['id']}")

    payload = response.json()
    assert response.status_code == 200
    assert len(payload["health"]) == 8
    assert {value["dimension"] for value in payload["health"]} == {
        "problem_evidence",
        "outcome_clarity",
        "strategic_alignment",
        "decision_quality",
        "execution_progress",
        "dependency_health",
        "measurement_readiness",
        "learning_velocity",
    }
    assert "score" not in str(payload).casefold()
    execution = next(
        value for value in payload["health"] if value["dimension"] == "execution_progress"
    )
    assert execution["state"] == "unknown"
    assert "activity records do not establish" in execution["explanation"].casefold()


def test_missing_outcome_is_an_initiative_gap_not_a_pm_performance_claim() -> None:
    with TestClient(_app()) as api:
        _initiative(api)
        refresh = api.post("/v1/management/refresh")
        team = api.get("/v1/team")
        attention = api.get("/v1/attention")

    signal = next(
        item for item in refresh.json()["signals"] if item["signal_type"] == "outcome_gap"
    )
    assert signal["subject_type"] == "initiative"
    assert signal["epistemic_level"] == "derived_signal"
    assert "does not prove" in " ".join(signal["limitations"]).casefold()
    assert len(team.json()) == 1
    assert "employee score" in " ".join(team.json()[0]["limitations"]).casefold()
    assert attention.json()[0]["management_signal_id"] == signal["id"]


def test_positive_outcome_signal_preserves_attribution_limits() -> None:
    with TestClient(_app()) as api:
        initiative = _initiative(api)
        outcome = api.post(
            "/v1/outcomes",
            json={
                "name": "Export completion increased",
                "outcome_type": "product",
                "metric": "completion rate",
                "target": "80%",
                "current": "82%",
                "initiative_ids": [initiative["id"]],
                "status": "achieved",
                "attribution": "correlated",
                "evidence_ids": ["research:export-analysis"],
            },
        )
        signals = api.post("/v1/management/refresh").json()["signals"]

    assert outcome.status_code == 201
    assert outcome.json()["attribution"] == "correlated"
    strength = next(item for item in signals if item["signal_type"] == "strength")
    assert "causal attribution" in " ".join(strength["limitations"]).casefold()
    assert strength["evidence_ids"] == ["research:export-analysis"]


def test_resolved_outcome_gap_is_marked_outdated_and_leaves_attention() -> None:
    with TestClient(_app()) as api:
        initiative = _initiative(api)
        gap = next(
            item
            for item in api.post("/v1/management/refresh").json()["signals"]
            if item["signal_type"] == "outcome_gap"
        )
        api.post(
            "/v1/outcomes",
            json={
                "name": "Export completion",
                "outcome_type": "product",
                "metric": "completion rate",
                "target": "80%",
                "initiative_ids": [initiative["id"]],
            },
        )
        refreshed = api.post("/v1/management/refresh").json()["signals"]
        attention = api.get("/v1/attention").json()

    prior = next(item for item in refreshed if item["id"] == gap["id"])
    assert prior["status"] == "outdated"
    assert all(item["management_signal_id"] != gap["id"] for item in attention)


def test_pattern_signal_requires_three_independent_initiatives() -> None:
    with TestClient(_app()) as api:
        for index in range(2):
            _initiative(api, f"Initiative {index}")
        first = api.post("/v1/management/refresh").json()["signals"]
        _initiative(api, "Initiative 3")
        second = api.post("/v1/management/refresh").json()["signals"]

    assert not any(item["signal_type"] == "coaching_opportunity" for item in first)
    coaching = [item for item in second if item["signal_type"] == "coaching_opportunity"]
    assert len(coaching) == 1
    assert len(coaching[0]["evidence_ids"]) == 3
    assert "not a conclusion about skill" in " ".join(coaching[0]["limitations"]).casefold()


def test_commitment_drift_requires_reason_and_preserves_history() -> None:
    with TestClient(_app()) as api:
        commitment = api.post(
            "/v1/commitments",
            json={
                "description": "Ship export audit view",
                "owner_id": "pm-1",
                "source": "explicit_user",
                "due_at": "2026-09-01T00:00:00Z",
                "status": "committed",
            },
        ).json()
        rejected = api.patch(
            f"/v1/commitments/{commitment['id']}",
            json={"due_at": "2026-09-15T00:00:00Z"},
        )
        changed = api.patch(
            f"/v1/commitments/{commitment['id']}",
            json={
                "due_at": "2026-09-15T00:00:00Z",
                "reason": "Dependency owner confirmed a later API date.",
                "source": "manager_context",
            },
        )

    assert rejected.status_code == 422
    assert changed.status_code == 200
    assert changed.json()["history"][0]["reason"].startswith("Dependency owner")


def test_signal_correction_is_auditable_and_removes_attention_item() -> None:
    with TestClient(_app()) as api:
        _initiative(api)
        signal = api.post("/v1/management/refresh").json()["signals"][0]
        corrected = api.post(
            f"/v1/management/signals/{signal['id']}/corrections",
            json={"action": "disagree", "context": "Outcome is tracked in a system not connected."},
        )
        corrections = api.get(f"/v1/management/signals/{signal['id']}/corrections")
        attention = api.get("/v1/attention")

    assert corrected.status_code == 200
    assert corrected.json()["signal"]["status"] == "disagreed"
    assert corrections.json()[0]["prior_interpretation"] is None
    assert corrections.json()[0]["context"].startswith("Outcome is tracked")
    assert attention.json() == []


def test_one_on_one_brief_is_traceable_and_contains_no_score() -> None:
    with TestClient(_app()) as api:
        _initiative(api)
        response = api.post("/v1/management/one-on-one", json={"pm_id": "pm-1", "weeks": 4})
        artifact = response.json()["artifact"]
        trace = api.get(f"/v1/runs/{artifact['agent_run_id']}/traces")

    assert response.status_code == 200
    assert artifact["artifact_type"] == "management_brief"
    assert artifact["workflow_name"] == "prepare_one_on_one"
    assert len(artifact["source_ids"]) >= 1
    assert "score" not in response.json()["brief"]
    assert "score" not in artifact["structured_data"]
    assert trace.status_code == 200
    assert trace.json()["events"][-1]["event_type"] == "run.completed"


def test_management_data_is_tenant_scoped() -> None:
    tenant_a = "00000000-0000-4000-8000-000000000010"
    tenant_b = "00000000-0000-4000-8000-000000000020"
    with TestClient(_app()) as api:
        item = api.post("/v1/initiatives", json={"name": "Private", "tenant_id": tenant_a}).json()
        hidden = api.get(f"/v1/initiatives/{item['id']}?tenant_id={tenant_b}")
        list_hidden = api.get(f"/v1/initiatives?tenant_id={tenant_b}")

    assert hidden.status_code == 404
    assert list_hidden.json() == []
