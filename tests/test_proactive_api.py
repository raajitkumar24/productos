from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from productos.api import create_app
from productos.config import Settings


def _app():
    return create_app(
        Settings(database_url="sqlite+aiosqlite:///:memory:", database_auto_create=True)
    )


def _initiative(api: TestClient, name: str = "Evidence gap") -> dict[str, object]:
    response = api.post(
        "/v1/initiatives",
        json={"name": name, "problem": "The outcome has not yet been documented."},
    )
    assert response.status_code == 201
    return response.json()


def test_notifications_default_off_and_explain_suppression() -> None:
    with TestClient(_app()) as api:
        _initiative(api)
        response = api.post("/v1/proactive/risk-scan", json={})
        preferences = api.get("/v1/proactive/preferences")

    assert response.status_code == 200
    assert response.json()["notifications"] == []
    assert response.json()["suppressed"] == ["notifications disabled by user preference"]
    assert preferences.json()["enabled"] is False


def test_novel_material_actionable_change_notifies_once() -> None:
    with TestClient(_app()) as api:
        _initiative(api)
        enabled = api.patch("/v1/proactive/preferences", json={"enabled": True})
        first = api.post("/v1/proactive/risk-scan", json={})
        second = api.post("/v1/proactive/risk-scan", json={})
        notifications = api.get("/v1/proactive/notifications")

    assert enabled.status_code == 200
    assert len(first.json()["notifications"]) == 1
    assert first.json()["notifications"][0]["level"] == "high"
    assert first.json()["notifications"][0]["evidence_ids"]
    assert second.json()["changes"] == []
    assert second.json()["notifications"] == []
    assert len(notifications.json()) == 1


def test_notification_daily_cap_prevents_spam() -> None:
    with TestClient(_app()) as api:
        _initiative(api, "First gap")
        _initiative(api, "Second gap")
        api.patch(
            "/v1/proactive/preferences",
            json={"enabled": True, "maximum_per_day": 1},
        )
        response = api.post("/v1/proactive/risk-scan", json={})

    assert len(response.json()["notifications"]) == 1
    assert any("daily notification limit" in item for item in response.json()["suppressed"])


def test_quiet_hours_suppress_delivery() -> None:
    now = datetime(2026, 8, 20, 22, 0, tzinfo=UTC)
    with TestClient(_app()) as api:
        _initiative(api)
        api.patch(
            "/v1/proactive/preferences",
            json={
                "enabled": True,
                "timezone": "UTC",
                "quiet_hours_start": "21:00:00",
                "quiet_hours_end": "07:00:00",
            },
        )
        response = api.post("/v1/proactive/risk-scan", json={"now": now.isoformat()})

    assert response.json()["notifications"] == []
    assert response.json()["suppressed"] == ["notification suppressed during quiet hours"]


def test_daily_brief_is_evidence_limited_and_traceable() -> None:
    with TestClient(_app()) as api:
        _initiative(api)
        response = api.post("/v1/proactive/daily-brief", json={})
        payload = response.json()
        trace = api.get(f"/v1/runs/{payload['artifact']['agent_run_id']}/traces")

    assert response.status_code == 200
    assert payload["artifact"]["artifact_type"] == "product_brief"
    assert payload["artifact"]["workflow_name"] == "daily_product_brief"
    assert payload["brief"]["evidence_ids"]
    assert "does not prove" in " ".join(payload["brief"]["evidence_limitations"])
    assert trace.json()["events"][-1]["event_type"] == "run.completed"


def test_scheduler_runs_only_due_enabled_schedule_and_advances_it() -> None:
    now = datetime(2026, 8, 20, 8, 30, tzinfo=UTC)
    with TestClient(_app()) as api:
        schedule = api.post(
            "/v1/proactive/schedules",
            json={
                "kind": "daily_product_brief",
                "frequency": "daily",
                "enabled": True,
                "timezone": "UTC",
                "local_time": "08:30:00",
                "next_run_at": (now - timedelta(minutes=1)).isoformat(),
            },
        )
        run = api.post("/v1/proactive/run", json={"now": now.isoformat()})
        schedules = api.get("/v1/proactive/schedules")
        trace = api.get(f"/v1/runs/{run.json()['run_id']}/traces")

    assert schedule.status_code == 201
    assert run.json()["schedules_evaluated"] == 1
    assert run.json()["schedules_run"] == 1
    assert len(run.json()["artifacts_created"]) == 1
    assert datetime.fromisoformat(schedules.json()[0]["next_run_at"]) > now
    assert trace.json()["events"][-1]["event_type"] == "run.completed"


def test_home_and_proactive_data_are_tenant_scoped() -> None:
    tenant_a = "00000000-0000-4000-8000-000000000010"
    tenant_b = "00000000-0000-4000-8000-000000000020"
    with TestClient(_app()) as api:
        api.post("/v1/initiatives", json={"name": "Private", "tenant_id": tenant_a})
        home_a = api.get(f"/v1/home?tenant_id={tenant_a}")
        home_b = api.get(f"/v1/home?tenant_id={tenant_b}")
        invalid = api.post(
            "/v1/proactive/schedules",
            json={
                "kind": "risk_scan",
                "frequency": "daily",
                "timezone": "Mars/Olympus",
                "next_run_at": datetime.now(UTC).isoformat(),
            },
        )

    assert len(home_a.json()["things_needing_attention"]) == 1
    assert home_b.json()["things_needing_attention"] == []
    assert invalid.status_code == 422
    assert "Unknown timezone" in invalid.json()["detail"]


def test_risk_and_decision_scans_keep_their_categories_separate() -> None:
    now = datetime.now(UTC)
    with TestClient(_app()) as api:
        _initiative(api)
        api.post(
            "/v1/decisions",
            json={
                "title": "Review launch architecture",
                "problem": "Validate the accepted approach",
                "context": "Evidence may have changed",
                "decision": "Retain the current architecture",
                "rationale": "It remains inspectable",
                "status": "accepted",
                "review_at": "2020-01-01T00:00:00Z",
                "evidence": ["decision-record:architecture"],
            },
        )
        api.patch("/v1/proactive/preferences", json={"enabled": True})
        risk = api.post("/v1/proactive/risk-scan", json={})
        api.post(
            "/v1/proactive/schedules",
            json={
                "kind": "decision_review_scan",
                "frequency": "daily",
                "enabled": True,
                "next_run_at": (now - timedelta(minutes=1)).isoformat(),
            },
        )
        api.post("/v1/proactive/run", json={"now": now.isoformat()})
        notifications = api.get("/v1/proactive/notifications").json()

    assert all(item["subject_type"] != "decision" for item in risk.json()["changes"])
    assert {item["category"] for item in notifications} == {"outcome_gap", "review_due"}
