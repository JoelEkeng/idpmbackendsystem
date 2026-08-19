"""Aggregate, cached stats for the admin dashboard.

Rather than have the frontend fetch full members/attendance lists just to
read `.length`, this exposes cheap SQL COUNT()s (and the finance summary
already computed elsewhere) behind a single Redis-cached endpoint.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_get_json, cache_set_json
from app.core.database import get_db
from app.models.attendance import Attendance
from app.models.finance import FinanceTransaction, PaymentStatus
from app.models.group import Group
from app.models.service import Service
from app.models.user import User
from app.models.profile import Profile
from app.utils.auth import get_current_user
from app.utils.permissions import is_admin

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

_ADMIN_SUMMARY_CACHE_KEY = "dashboard:admin-summary"
_ADMIN_SUMMARY_TTL = 60  # seconds


@router.get("/admin-summary")
async def admin_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")

    cached = await cache_get_json(_ADMIN_SUMMARY_CACHE_KEY)
    if cached is not None:
        return cached

    # All counts are independent; run them concurrently.
    (
        total_members,
        total_groups,
        total_services,
        total_attendance,
        total_revenue,
    ) = await asyncio.gather(
        db.scalar(select(func.count()).select_from(Profile)),
        db.scalar(select(func.count()).select_from(Group)),
        db.scalar(select(func.count()).select_from(Service)),
        db.scalar(select(func.count()).select_from(Attendance)),
        db.scalar(
            select(func.coalesce(func.sum(FinanceTransaction.amount), 0)).where(
                FinanceTransaction.status == PaymentStatus.success
            )
        ),
    )

    payload = {
        "total_members": total_members or 0,
        "total_groups": total_groups or 0,
        "total_services": total_services or 0,
        "total_attendance": total_attendance or 0,
        "total_revenue": float(total_revenue or 0),
    }

    await cache_set_json(_ADMIN_SUMMARY_CACHE_KEY, payload, ttl=_ADMIN_SUMMARY_TTL)
    return payload
