from __future__ import annotations

from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

import httpx
import jwt
from pydantic import BaseModel, Field

from productos.config import Settings


class AuthenticationError(RuntimeError):
    pass


class AuthenticatedPrincipal(BaseModel):
    subject: str
    user_id: UUID
    tenant_id: UUID
    scopes: set[str] = Field(default_factory=set)


current_principal: ContextVar[AuthenticatedPrincipal | None] = ContextVar(
    "productos_current_principal", default=None
)


class TokenValidator(Protocol):
    async def validate(self, token: str) -> AuthenticatedPrincipal: ...


class OIDCTokenValidator:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        jwks: dict[str, object] | None = None,
    ) -> None:
        self._issuer = str(settings.oidc_issuer)
        self._audience = str(settings.oidc_audience)
        self._jwks_url = str(settings.oidc_jwks_url)
        self._user_claim = settings.oidc_user_claim
        self._tenant_claim = settings.oidc_tenant_claim
        self._cache_duration = timedelta(seconds=settings.oidc_jwks_cache_seconds)
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(10))
        self._owns_client = client is None
        self._jwks = jwks
        self._jwks_expires_at = (
            datetime.max.replace(tzinfo=UTC) if jwks else datetime.min.replace(tzinfo=UTC)
        )

    async def validate(self, token: str) -> AuthenticatedPrincipal:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not header.get("kid"):
                raise AuthenticationError("Token algorithm or key identifier is not allowed")
            key = await self._key(str(header["kid"]))
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub"]},
            )
            scope_value = claims.get("scope", "")
            scopes = set(scope_value.split()) if isinstance(scope_value, str) else set()
            return AuthenticatedPrincipal(
                subject=str(claims["sub"]),
                user_id=UUID(str(claims[self._user_claim])),
                tenant_id=UUID(str(claims[self._tenant_claim])),
                scopes=scopes,
            )
        except AuthenticationError:
            raise
        except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
            raise AuthenticationError("Bearer token is invalid") from exc

    async def _key(self, kid: str) -> object:
        jwks = await self._get_jwks()
        keys = jwks.get("keys")
        if not isinstance(keys, list):
            raise AuthenticationError("Identity provider key set is invalid")
        record = next(
            (item for item in keys if isinstance(item, dict) and item.get("kid") == kid), None
        )
        if record is None:
            self._jwks_expires_at = datetime.min.replace(tzinfo=UTC)
            jwks = await self._get_jwks()
            refreshed_keys = jwks.get("keys")
            keys = refreshed_keys if isinstance(refreshed_keys, list) else []
            record = next(
                (item for item in keys if isinstance(item, dict) and item.get("kid") == kid),
                None,
            )
        if not isinstance(record, dict):
            raise AuthenticationError("Bearer token signing key was not found")
        try:
            return jwt.PyJWK.from_dict(record, algorithm="RS256").key
        except (jwt.PyJWTError, ValueError) as exc:
            raise AuthenticationError("Identity provider signing key is invalid") from exc

    async def _get_jwks(self) -> dict[str, object]:
        now = datetime.now(UTC)
        if self._jwks is not None and now < self._jwks_expires_at:
            return self._jwks
        try:
            response = await self._client.get(self._jwks_url)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthenticationError("Identity provider keys are unavailable") from exc
        if not isinstance(payload, dict):
            raise AuthenticationError("Identity provider key set is invalid")
        self._jwks = payload
        self._jwks_expires_at = now + self._cache_duration
        return payload

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
