from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.attendance import Attendance
from app.models.profile import Profile
from app.models.service import Service

router = APIRouter(prefix="/attendance", tags=["Attendance"])


@router.post("/checkin")
async def fingerprint_checkin(
    fingerprint_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint called by fingerprint device when a user scans.
    """

    now = datetime.utcnow()
    today = now.date()
    current_time = now.time()

    # 1️⃣ Find profile linked to fingerprint
    stmt = select(Profile).where(Profile.fingerprint_id == fingerprint_id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Fingerprint not registered"
        )

    # 2️⃣ Find active service
    stmt = select(Service).where(
        Service.date == today,
        Service.grace_before_time <= current_time,
        Service.grace_end_time >= current_time
    )

    result = await db.execute(stmt)
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=404,
            detail="No active service at this time"
        )

    # 3️⃣ Prevent duplicate attendance
    stmt = select(Attendance).where(
        Attendance.profile_id == profile.id,
        Attendance.service_id == service.id
    )

    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        return {
            "message": "Attendance already recorded",
            "service_id": str(service.id)
        }

    # 4️⃣ Record attendance
    attendance = Attendance(
        profile_id=profile.id,
        service_id=service.id,
        check_in_time=now
    )

    db.add(attendance)
    await db.commit()
    await db.refresh(attendance)

    return {
        "message": "Attendance recorded successfully",
        "service_id": str(service.id),
        "profile_id": str(profile.id),
        "check_in_time": attendance.check_in_time
    }


@router.get("/service/{service_id}")
async def get_service_attendance(
    service_id: str,
    db: AsyncSession = Depends(get_db)
):

    stmt = select(Attendance).where(
        Attendance.service_id == service_id
    )

    result = await db.execute(stmt)

    return result.scalars().all()