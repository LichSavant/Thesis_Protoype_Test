from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    database_url: str = "sqlite:///./database/phishing_defense.db"
    email_open_deduplication_seconds: int = Field(default=5, ge=1, le=60)
    supabase_url: str | None = None
    supabase_service_role_key: str | None = Field(default=None, repr=False)

    model_config = SettingsConfigDict(env_file="backend/.env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
