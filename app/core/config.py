from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict
from pydantic import AnyUrl
from functools import lru_cache
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        extra="ignore",
    )

    APP_NAME: str = "Church CMS"
    API_PREFIX: str = "/api/v1"

    DATABASE_URL: AnyUrl
    REDIS_URL: str

    BETTERAUTH_PUBLIC_KEY: str
    JWT_ALGORITHM: str = "RS256"

    SENTRY_DSN: str | None = None
    SENTRY_ENVIRONMENT: str = "development"
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    RATE_LIMIT: str = "100/minute"


@lru_cache
def get_settings():
    return Settings()