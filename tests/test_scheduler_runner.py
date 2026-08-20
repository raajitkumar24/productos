from pathlib import Path
from uuid import UUID

import httpx
import pytest
import yaml

from productos.operations.scheduler import SchedulerRunnerSettings, run_scheduler


def test_scheduler_runner_sends_explicit_scope_and_bearer_token(tmp_path: Path) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("short-lived-token")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer short-lived-token"
        assert request.url.path == "/v1/proactive/run"
        assert b'"tenant_id"' in request.content
        return httpx.Response(
            200,
            json={
                "schedules_evaluated": 4,
                "schedules_run": 1,
                "notifications_created": [],
            },
        )

    settings = SchedulerRunnerSettings(
        api_url="https://productos.example",
        tenant_id=UUID("00000000-0000-4000-8000-000000000010"),
        user_id=UUID("00000000-0000-4000-8000-000000000001"),
        bearer_token_file=token_file,
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = run_scheduler(settings, client)

    assert result["schedules_run"] == 1
    assert "short-lived-token" not in repr(settings)


def test_scheduler_runner_requires_exactly_one_token_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        SchedulerRunnerSettings(
            api_url="https://productos.example",
            tenant_id=UUID(int=1),
            user_id=UUID(int=2),
        )
    with pytest.raises(ValueError, match="exactly one"):
        SchedulerRunnerSettings(
            api_url="https://productos.example",
            tenant_id=UUID(int=1),
            user_id=UUID(int=2),
            bearer_token="token",
            bearer_token_file=tmp_path / "token",
        )


def test_kubernetes_cronjob_is_non_concurrent_scoped_and_contains_no_token() -> None:
    manifest_path = Path("deploy/kubernetes/proactive-cronjob.yaml")
    manifest = yaml.safe_load(manifest_path.read_text())
    rendered = manifest_path.read_text().casefold()

    assert manifest["kind"] == "CronJob"
    assert manifest["spec"]["concurrencyPolicy"] == "Forbid"
    container = manifest["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
    names = {item["name"] for item in container["env"]}
    assert {"PRODUCTOS_SCHEDULER_TENANT_ID", "PRODUCTOS_SCHEDULER_USER_ID"} <= names
    assert "bearer ey" not in rendered
    assert "secretname: productos-scheduler-identity" in rendered
