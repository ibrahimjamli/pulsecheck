"""Runtime configuration, sourced from the environment.

Every setting has a development-safe default so the app boots with no
environment at all, which keeps `docker run` and the test suite simple.
Production overrides arrive as environment variables from the container
runtime (compose, Kubernetes ConfigMap/Secret).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PULSECHECK_", env_file=".env")

    # SQLite keeps local runs dependency-free; compose and Kubernetes both
    # override this with an asyncpg URL pointing at Postgres.
    database_url: str = "sqlite+aiosqlite:///./pulsecheck.db"

    # Outbound probe budget. Kept short so a hung target cannot stall a worker.
    probe_timeout_seconds: float = 5.0
    probe_user_agent: str = "pulsecheck/0.1 (+https://github.com/ibrahimjamli/pulsecheck)"

    log_level: str = "INFO"
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    """Cached so every request shares one parsed Settings instance."""
    return Settings()
