import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from productos.api import create_app
from productos.config import Settings
from productos.security import AuthenticationError, OIDCTokenValidator

USER_ID = "00000000-0000-4000-8000-000000000001"
TENANT_ID = "00000000-0000-4000-8000-000000000010"


def _auth() -> tuple[Settings, OIDCTokenValidator, object]:
    settings = Settings(
        environment="testing",
        database_url="sqlite+aiosqlite:///:memory:",
        database_auto_create=True,
        auth_enabled=True,
        oidc_issuer="https://identity.example/",
        oidc_audience="productos-api",
        oidc_jwks_url="https://identity.example/.well-known/jwks.json",
    )
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
    validator = OIDCTokenValidator(settings, jwks={"keys": [public_jwk]})
    return settings, validator, private_key


def _token(private_key: object, **overrides: object) -> str:
    now = datetime.now(UTC)
    claims = {
        "iss": "https://identity.example/",
        "aud": "productos-api",
        "sub": "identity-user-123",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "productos_user_id": USER_ID,
        "productos_tenant_id": TENANT_ID,
        "scope": "openid",
        **overrides,
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


@pytest.mark.asyncio
async def test_oidc_validator_verifies_signature_audience_and_scope_claims() -> None:
    _, validator, key = _auth()
    principal = await validator.validate(_token(key))

    assert str(principal.user_id) == USER_ID
    assert str(principal.tenant_id) == TENANT_ID
    assert principal.subject == "identity-user-123"
    with pytest.raises(AuthenticationError):
        await validator.validate(_token(key, aud="another-api"))


def test_api_requires_bearer_token_and_binds_requested_scope_to_claims() -> None:
    settings, validator, key = _auth()
    with TestClient(create_app(settings, token_validator=validator)) as api:
        missing = api.get("/v1/home")
        headers = {"Authorization": f"Bearer {_token(key)}"}
        identity = api.get("/v1/auth/me", headers=headers)
        mismatched = api.get(
            "/v1/home?tenant_id=00000000-0000-4000-8000-000000000099",
            headers=headers,
        )
        scheduler_forbidden = api.post("/v1/proactive/run", json={}, headers=headers)
        evaluator_forbidden = api.post("/v1/evaluations/run", json={}, headers=headers)

    assert missing.status_code == 401
    assert identity.status_code == 200
    assert identity.json()["tenant_id"] == TENANT_ID
    assert mismatched.status_code == 403
    assert scheduler_forbidden.status_code == 403
    assert evaluator_forbidden.status_code == 403


def test_scheduler_accepts_explicit_workload_scope() -> None:
    settings, validator, key = _auth()
    token = _token(key, scope="productos:scheduler")
    with TestClient(create_app(settings, token_validator=validator)) as api:
        response = api.post(
            "/v1/proactive/run", json={}, headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    assert response.json()["schedules_evaluated"] == 0


def test_trace_access_is_tenant_scoped_after_authentication() -> None:
    settings, validator, key = _auth()
    first_headers = {"Authorization": f"Bearer {_token(key)}"}
    other_tenant = "00000000-0000-4000-8000-000000000099"
    other_headers = {"Authorization": f"Bearer {_token(key, productos_tenant_id=other_tenant)}"}
    with TestClient(create_app(settings, token_validator=validator)) as api:
        chat = api.post("/v1/chat", json={"message": "Hello"}, headers=first_headers)
        run_id = json.loads(chat.text.splitlines()[1].removeprefix("data: "))["run_id"]
        hidden = api.get(f"/v1/runs/{run_id}/traces", headers=other_headers)

    assert hidden.status_code == 404


def test_production_configuration_fails_closed_without_authentication() -> None:
    with pytest.raises(ValueError, match="AUTH_ENABLED"):
        Settings(environment="production")


def test_production_configuration_rejects_development_storage_and_models() -> None:
    with pytest.raises(ValueError, match="MODEL_PROVIDER"):
        Settings(
            environment="production",
            auth_enabled=True,
            oidc_issuer="https://identity.example/",
            oidc_audience="productos-api",
            oidc_jwks_url="https://identity.example/jwks",
        )
