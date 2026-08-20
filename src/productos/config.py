from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PRODUCTOS_", extra="ignore")

    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./productos.db"
    database_auto_create: bool = True
    model_provider: Literal["development", "openai_compatible"] = "development"
    model_base_url: str | None = None
    model_api_key: SecretStr | None = None
    model_name: str | None = None
    model_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    model_max_output_tokens: int = Field(default=4096, ge=1, le=100_000)
    model_temperature: float = Field(default=0.1, ge=0, le=2)
    judge_base_url: str | None = None
    judge_api_key: SecretStr | None = None
    judge_model: str | None = None
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    runtime_version: str = "0.8.0"
    constitution_version: str = "1.0.0"
    memory_policy_version: str = "1.0.0"
    retrieval_policy_version: str = "1.0.0"
    default_user_id: UUID = UUID("00000000-0000-4000-8000-000000000001")
    default_tenant_id: UUID = UUID("00000000-0000-4000-8000-000000000010")
    embedding_provider: Literal["deterministic", "openai_compatible"] = "deterministic"
    embedding_base_url: str | None = None
    embedding_api_key: SecretStr | None = None
    embedding_model: str | None = None
    embedding_dimension: int = 128
    knowledge_chunk_tokens: int = 500
    knowledge_chunk_overlap_tokens: int = 60
    retrieval_limit: int = 8
    tool_contract_version: str = "1.0.0"
    mcp_adapter_version: str = "1.0.0"
    max_tool_calls: int = 8
    max_tool_iterations: int = 3
    max_tool_retries: int = 1
    max_tool_latency_seconds: float = 20.0
    atlassian_read_enabled: bool = False
    atlassian_mcp_url: str | None = None
    atlassian_mcp_tool_map: dict[str, str] = Field(default_factory=dict)
    auth_enabled: bool = False
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_user_claim: str = "productos_user_id"
    oidc_tenant_claim: str = "productos_tenant_id"
    oidc_jwks_cache_seconds: int = Field(default=300, ge=30, le=86_400)
    evaluation_metrics_version: str = "1.0.0"

    @model_validator(mode="after")
    def validate_provider_configuration(self) -> "Settings":
        if self.environment == "production":
            production_errors = []
            if not self.auth_enabled:
                production_errors.append("PRODUCTOS_AUTH_ENABLED must be true")
            if self.model_provider == "development":
                production_errors.append("PRODUCTOS_MODEL_PROVIDER must be production-capable")
            if self.embedding_provider == "deterministic":
                production_errors.append("PRODUCTOS_EMBEDDING_PROVIDER must be production-capable")
            if self.database_auto_create:
                production_errors.append("PRODUCTOS_DATABASE_AUTO_CREATE must be false")
            if not self.database_url.startswith("postgresql+asyncpg://"):
                production_errors.append("PRODUCTOS_DATABASE_URL must use PostgreSQL/asyncpg")
            secure_urls = [
                self.model_base_url,
                self.embedding_base_url or self.model_base_url,
                self.oidc_issuer,
                self.oidc_jwks_url,
            ]
            if any(value and not value.startswith("https://") for value in secure_urls):
                production_errors.append("Production provider and OIDC URLs must use HTTPS")
            if production_errors:
                raise ValueError("; ".join(production_errors))
        if self.auth_enabled:
            missing = [
                name
                for name, value in {
                    "PRODUCTOS_OIDC_ISSUER": self.oidc_issuer,
                    "PRODUCTOS_OIDC_AUDIENCE": self.oidc_audience,
                    "PRODUCTOS_OIDC_JWKS_URL": self.oidc_jwks_url,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError("OIDC authentication requires: " + ", ".join(missing))
        if self.model_provider != "development":
            missing = [
                name
                for name, value in {
                    "PRODUCTOS_MODEL_BASE_URL": self.model_base_url,
                    "PRODUCTOS_MODEL_API_KEY": self.model_api_key,
                    "PRODUCTOS_MODEL_NAME": self.model_name,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError("Production model provider requires: " + ", ".join(missing))
        if self.embedding_provider != "deterministic":
            missing = [
                name
                for name, value in {
                    "PRODUCTOS_EMBEDDING_MODEL": self.embedding_model,
                    "PRODUCTOS_EMBEDDING_API_KEY": (self.embedding_api_key or self.model_api_key),
                    "PRODUCTOS_EMBEDDING_BASE_URL": (
                        self.embedding_base_url or self.model_base_url
                    ),
                }.items()
                if not value
            ]
            if missing:
                raise ValueError("Production embedding provider requires: " + ", ".join(missing))
        if any((self.judge_base_url, self.judge_api_key, self.judge_model)):
            missing = [
                name
                for name, value in {
                    "PRODUCTOS_JUDGE_BASE_URL": self.judge_base_url,
                    "PRODUCTOS_JUDGE_API_KEY": self.judge_api_key,
                    "PRODUCTOS_JUDGE_MODEL": self.judge_model,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError("Judge provider requires: " + ", ".join(missing))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
