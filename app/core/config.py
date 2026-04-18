from pydantic_settings import BaseSettings
from pydantic import AnyUrl
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "Church CMS"
    API_PREFIX: str = "/api/v1"

    DATABASE_URL: AnyUrl
    REDIS_URL: str

    BETTERAUTH_PUBLIC_KEY: str
    JWT_ALGORITHM: str = "RS256"

    RATE_LIMIT: str = "100/minute"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings():
    return Settings()