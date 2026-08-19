import redis.asyncio as redis
from app.core.config import get_settings

settings = get_settings()

redis_client = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    max_connections=settings.REDIS_MAX_CONNECTIONS,
    health_check_interval=settings.REDIS_HEALTH_CHECK_INTERVAL,
    retry_on_timeout=True,
    socket_keepalive=True,
)
