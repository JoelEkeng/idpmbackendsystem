import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
import sentry_sdk
from app.core.config import get_settings
from app.core.database import engine
from app.core.middleware import SecurityHeadersMiddleware, RateLimitMiddleware, RequestMetricsMiddleware
from app.core.redis import redis_client
from app.api.v1.router import (
    profile,
    group,
    user,
    equipment,
    service, attendance, finance, dashboard, visitor
)
import dotenv
dotenv.load_dotenv()


settings = get_settings()
logger = logging.getLogger(__name__)


if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=settings.SENTRY_SEND_DEFAULT_PII,
        enable_logs=settings.SENTRY_ENABLE_LOGS,
    )

app = FastAPI(title=settings.APP_NAME)

# Order matters: last-added middleware runs first (outermost).
# Rate limit before doing any work; add security headers to every response.
app.add_middleware(
    RateLimitMiddleware,
    rate=settings.RATE_LIMIT,
    exempt_paths=("/health", "/docs", "/openapi.json", "/redoc"),
    strict_rates={
        "/api/v1/finance": settings.FINANCE_RATE_LIMIT,
        "/api/v1/attendance/checkin": settings.ATTENDANCE_CHECKIN_RATE_LIMIT,
        "/api/v1/visitors": settings.VISITOR_RATE_LIMIT,
    },
)
app.add_middleware(SecurityHeadersMiddleware)
if settings.REQUEST_METRICS_ENABLED:
    app.add_middleware(RequestMetricsMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "x-paystack-signature"],
)


@app.on_event("shutdown")
async def _close_redis():
    try:
        await redis_client.aclose()
    except Exception:
        pass

app.include_router(group.router, prefix=settings.API_PREFIX)
app.include_router(profile.router, prefix=settings.API_PREFIX)
app.include_router(user.router, prefix=settings.API_PREFIX)
app.include_router(equipment.router, prefix=settings.API_PREFIX)
app.include_router(service.router, prefix=settings.API_PREFIX)
app.include_router(attendance.router, prefix=settings.API_PREFIX)
app.include_router(finance.router, prefix=settings.API_PREFIX)
app.include_router(dashboard.router, prefix=settings.API_PREFIX)
app.include_router(visitor.router, prefix=settings.API_PREFIX)

@app.get("/health")
async def health():
    return {"status": "ok"}


async def _database_ready() -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Database readiness check failed: %s", exc)
        return False


async def _redis_ready() -> bool:
    try:
        return bool(await redis_client.ping())
    except Exception:
        return False


@app.get("/health/ready")
async def readiness():
    results = await asyncio.gather(
        asyncio.wait_for(
            _database_ready(),
            timeout=settings.READINESS_TIMEOUT_SECONDS,
        ),
        asyncio.wait_for(
            _redis_ready(),
            timeout=settings.READINESS_TIMEOUT_SECONDS,
        ),
        return_exceptions=True,
    )
    database = results[0] is True
    redis = results[1] is True

    payload = {
        "status": "ready" if database and redis else "not_ready",
        "dependencies": {
            "database": "ok" if database else "unavailable",
            "redis": "ok" if redis else "unavailable",
        },
    }
    if database and redis:
        return payload
    return JSONResponse(status_code=503, content=payload)


@app.on_event("startup")
async def startup():
    try:
        await redis_client.ping()
        print("✅ Connected to Redis")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
