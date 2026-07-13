from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sentry_sdk
from app.core.config import get_settings
from app.core.middleware import SecurityHeadersMiddleware, RateLimitMiddleware
from app.core.redis import redis_client
from app.api.v1.router import (
    profile,
    group,
    user,
    equipment,
    service, attendance, finance
)
import dotenv
dotenv.load_dotenv()


settings = get_settings()


if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.SENTRY_ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        # Add data like request headers and IP for users,
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=True,
        enable_logs=True,
    )

app = FastAPI(title=settings.APP_NAME)

# Order matters: last-added middleware runs first (outermost).
# Rate limit before doing any work; add security headers to every response.
app.add_middleware(
    RateLimitMiddleware,
    rate=settings.RATE_LIMIT,
    exempt_paths=("/health", "/docs", "/openapi.json", "/redoc"),
)
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.on_event("startup")
async def startup():
    try:
        await redis_client.ping()
        print("✅ Connected to Redis")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
