from pathlib import Path
from uuid import UUID

import httpx
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SchedulerRunnerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PRODUCTOS_SCHEDULER_", extra="ignore")

    api_url: str
    tenant_id: UUID
    user_id: UUID
    bearer_token: SecretStr | None = None
    bearer_token_file: Path | None = None
    timeout_seconds: float = Field(default=30, gt=0, le=120)

    @model_validator(mode="after")
    def require_one_token_source(self) -> "SchedulerRunnerSettings":
        if bool(self.bearer_token) == bool(self.bearer_token_file):
            raise ValueError("Configure exactly one scheduler bearer token source")
        return self

    def token(self) -> str:
        if self.bearer_token is not None:
            return self.bearer_token.get_secret_value()
        if self.bearer_token_file is None:
            raise RuntimeError("Scheduler bearer token is unavailable")
        value = self.bearer_token_file.read_text().strip()
        if not value:
            raise RuntimeError("Scheduler bearer token file is empty")
        return value


def run_scheduler(
    settings: SchedulerRunnerSettings, client: httpx.Client | None = None
) -> dict[str, object]:
    owns_client = client is None
    configured_client = client or httpx.Client(timeout=settings.timeout_seconds)
    try:
        response = configured_client.post(
            f"{settings.api_url.rstrip('/')}/v1/proactive/run",
            headers={"Authorization": f"Bearer {settings.token()}"},
            json={
                "tenant_id": str(settings.tenant_id),
                "user_id": str(settings.user_id),
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Scheduler API returned an invalid response")
        return payload
    except httpx.HTTPError as exc:
        raise RuntimeError("Scheduler invocation failed safely") from exc
    finally:
        if owns_client:
            configured_client.close()


def main() -> None:
    result = run_scheduler(SchedulerRunnerSettings())
    print(
        "Scheduler completed: "
        f"evaluated={result.get('schedules_evaluated', 0)} "
        f"run={result.get('schedules_run', 0)} "
        f"notifications={len(result.get('notifications_created', []))}"
    )


if __name__ == "__main__":
    main()
