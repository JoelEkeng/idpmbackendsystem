import json

from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict
from pydantic_settings import NoDecode
from pydantic import AnyUrl, field_validator
from functools import lru_cache
from pathlib import Path
from typing import Annotated


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

    # PostgreSQL connection-pool tuning. Defaults are safe for moderate traffic;
    # raise them for >1k concurrent users or heavy dashboards.
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_RECYCLE: int = 3600
    DB_POOL_TIMEOUT: int = 30
    DB_ECHO: bool = False

    # Redis connection pool tuning.
    REDIS_MAX_CONNECTIONS: int = 100
    REDIS_HEALTH_CHECK_INTERVAL: int = 30

    BETTERAUTH_PUBLIC_KEY: str
    JWT_ALGORITHM: str = "RS256"

    # Allowed browser origins for CORS. Accepts a comma-separated string or a
    # JSON list in the environment, e.g. "https://app.example.com,https://admin.example.com".
    CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    SENTRY_DSN: str | None = None
    SENTRY_ENVIRONMENT: str = "development"
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    RATE_LIMIT: str = "100/minute"

    # Only trust the X-Forwarded-For header when we know we're behind a
    # reverse proxy/load balancer that sets it itself (it's trivially
    # spoofable otherwise). Off by default.
    TRUST_PROXY_HEADERS: bool = False

    # Frontend origin used for building redirect/callback URLs (e.g. Paystack callback).
    FRONTEND_URL: str = "http://localhost:3000"

    # IP allow-list for the fingerprint access-control device hitting
    # /attendance/checkin. That endpoint can't use normal user sessions since
    # the device isn't a logged-in browser, so instead we trust it based on
    # its network source (exact IPs or CIDR ranges, comma-separated, e.g.
    # "192.168.1.50,10.0.0.0/24"). Empty means no device is allowed.
    DEVICE_ALLOWED_IPS: Annotated[list[str], NoDecode] = []

    @field_validator("CORS_ORIGINS", "DEVICE_ALLOWED_IPS", mode="before")
    @classmethod
    def _split_cors_origins(cls, v):
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            # Allow a JSON-style list too; otherwise treat as comma-separated.
            if s.startswith("["):
                try:
                    parsed = json.loads(s)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    return [str(origin).strip() for origin in parsed if str(origin).strip()]
                # Fall back to comma-splitting after stripping brackets/quotes.
                s = s.strip("[]")
            return [origin.strip().strip('"').strip("'") for origin in s.split(",") if origin.strip().strip('"').strip("'")]
        return v


@lru_cache
def get_settings():
    return Settings()