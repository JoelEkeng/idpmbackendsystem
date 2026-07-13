from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.cache import cache_get_json, cache_set_json, cache_delete
from app.models.attendance import Attendance
from app.models.profile import Profile
from app.models.service import Service
from app.models.group import Group, GroupMember
from app.models.enums import GroupMembershipStatus, RoleEnum
from app.models.user import User
from app.schemas.attendance import AttendanceRead
from app.utils.auth import get_current_user
from app.utils.permissions import is_admin
from sqlalchemy.orm import selectinload

from fastapi import Request
from uuid import UUID as UUIDType
import json


router = APIRouter(prefix="/attendance", tags=["Attendance"])


def _service_cache_key(service_id) -> str:
    return f"attendance:service:{service_id}"


@router.post("/checkin")
async def fingerprint_checkin(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    raw_body = await request.body()
    body_str = raw_body.decode()

    # Extract JSON from multipart
    start = body_str.find("{")
    end = body_str.rfind("}") + 1
    json_str = body_str[start:end]

    data = json.loads(json_str)
    event = data.get("AccessControllerEvent", {})

    # ✅ Filter only valid fingerprint events
    if not (
        event.get("majorEventType") == 5 and
        event.get("subEventType") == 38 and
        event.get("currentVerifyMode") == "fp"
    ):
        return {"status": "ignored"}

    fingerprint_id = event.get("employeeNoString")

    if not fingerprint_id:
        return {"status": "no fingerprint id"}

    # 🕒 Current time (server local; matches services scheduled in local time).
    now = datetime.now()
    today = now.date()

    # 👤 Find user
    stmt = select(Profile).where(Profile.fingerprint_id == fingerprint_id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(404, "User not found")

    # ⛪ Find active service for today, then filter by [start - grace_before, end + grace_after].
    stmt = select(Service).where(Service.date == today)
    result = await db.execute(stmt)
    services_today = result.scalars().all()

    service = None
    for s in services_today:
        start_dt = datetime.combine(today, s.start_time) - timedelta(
            minutes=s.grace_before_minutes or 0
        )
        end_dt = datetime.combine(today, s.end_time) + timedelta(
            minutes=s.grace_after_minutes or 0
        )
        if start_dt <= now <= end_dt:
            service = s
            break

    if not service:
        return {
            "status": "no_active_service",
            "message": "No service currently ongoing",
        }

    # 🚫 Prevent duplicate attendance
    stmt = select(Attendance).where(
        Attendance.profile_id == profile.id,
        Attendance.service_id == service.id,
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        return {
            "status": "duplicate",
            "message": "Attendance already recorded",
        }

    # ✅ Save attendance
    attendance = Attendance(
        profile_id=profile.id,
        service_id=service.id,
        check_in_time=now,
    )
    db.add(attendance)
    await db.commit()

    # Invalidate the cached attendance list for this service so the monitor
    # page reflects the new check-in on its next refresh.
    await cache_delete(_service_cache_key(service.id))

    return {
        "status": "success",
        "user": profile.fullname,
        "service_id": str(service.id),
        "service_date": str(service.date),
        "time": now.isoformat(),
    }

def _to_read(att: Attendance) -> AttendanceRead:
    """Turn a fully-loaded Attendance row into the enriched response."""
    return AttendanceRead(
        id=att.id,
        profile_id=att.profile_id,
        user_id=att.profile.user_id if att.profile else "",
        member_name=att.profile.fullname if att.profile else None,
        service_id=att.service_id,
        service_date=att.service.date if att.service else None,
        check_in_time=att.check_in_time,
    )


_ATTENDANCE_EAGER = (
    selectinload(Attendance.profile),
    selectinload(Attendance.service),
)


@router.get("", response_model=list[AttendanceRead])
async def list_all_attendance(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Admin-only: attendance records, newest first, paginated."""
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")

    stmt = (
        select(Attendance)
        .options(*_ATTENDANCE_EAGER)
        .order_by(Attendance.check_in_time.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return [_to_read(a) for a in result.scalars().all()]


@router.get("/user/{user_id}", response_model=list[AttendanceRead])
async def get_user_attendance(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attendance for a BetterAuth user id (resolves to the linked profile)."""
    profile_q = await db.execute(
        select(Profile).where(Profile.user_id == user_id)
    )
    profile = profile_q.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profile not found for user")

    own = user_id == current_user.id
    admin = is_admin(current_user)
    is_leader = False

    if not (own or admin):
        membership_q = await db.execute(
            select(GroupMember).where(
                GroupMember.user_id == user_id,
                GroupMember.status == GroupMembershipStatus.APPROVED,
            )
        )
        membership = membership_q.scalar_one_or_none()
        if membership:
            group = await db.get(Group, membership.group_id)
            is_leader = bool(group and group.leader_id == current_user.id)

    if not (own or admin or is_leader):
        raise HTTPException(403, "Not allowed")

    stmt = (
        select(Attendance)
        .options(*_ATTENDANCE_EAGER)
        .where(Attendance.profile_id == profile.id)
        .order_by(Attendance.check_in_time.desc())
    )
    result = await db.execute(stmt)
    return [_to_read(a) for a in result.scalars().all()]


@router.get("/me", response_model=list[AttendanceRead])
async def get_my_attendance(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Current user's own attendance history."""
    profile_q = await db.execute(
        select(Profile).where(Profile.user_id == current_user.id)
    )
    profile = profile_q.scalar_one_or_none()
    if not profile:
        return []

    stmt = (
        select(Attendance)
        .options(*_ATTENDANCE_EAGER)
        .where(Attendance.profile_id == profile.id)
        .order_by(Attendance.check_in_time.desc())
    )
    result = await db.execute(stmt)
    return [_to_read(a) for a in result.scalars().all()]


@router.get("/profile/{profile_id}", response_model=list[AttendanceRead])
async def get_profile_attendance(
    profile_id: UUIDType,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Attendance for a specific profile.
    Allowed if: it's your own profile, you're an admin, or you're the
    group leader of the group this profile belongs to.
    """
    profile = await db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")

    own = profile.user_id == current_user.id
    admin = is_admin(current_user)
    is_leader = False

    if not (own or admin):
        # Is this requester the leader of the group this profile belongs to?
        membership_q = await db.execute(
            select(GroupMember)
            .where(
                GroupMember.user_id == profile.user_id,
                GroupMember.status == GroupMembershipStatus.APPROVED,
            )
        )
        membership = membership_q.scalar_one_or_none()
        if membership:
            group = await db.get(Group, membership.group_id)
            is_leader = bool(group and group.leader_id == current_user.id)

    if not (own or admin or is_leader):
        raise HTTPException(403, "Not allowed to view this attendance")

    stmt = (
        select(Attendance)
        .options(*_ATTENDANCE_EAGER)
        .where(Attendance.profile_id == profile_id)
        .order_by(Attendance.check_in_time.desc())
    )
    result = await db.execute(stmt)
    return [_to_read(a) for a in result.scalars().all()]


@router.get("/group/{group_id}", response_model=list[AttendanceRead])
async def get_group_attendance(
    group_id: UUIDType,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Attendance for all APPROVED members of a group.
    Visible to that group's leader or to admins.
    """
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    if group.leader_id != current_user.id and not is_admin(current_user):
        raise HTTPException(403, "Only the group leader or an admin can view this")

    # Profile ids of approved members of this group.
    members_q = await db.execute(
        select(Profile.id)
        .join(GroupMember, GroupMember.user_id == Profile.user_id)
        .where(
            GroupMember.group_id == group_id,
            GroupMember.status == GroupMembershipStatus.APPROVED,
        )
    )
    profile_ids = [row[0] for row in members_q.all()]

    if not profile_ids:
        return []

    stmt = (
        select(Attendance)
        .options(*_ATTENDANCE_EAGER)
        .where(Attendance.profile_id.in_(profile_ids))
        .order_by(Attendance.check_in_time.desc())
    )
    result = await db.execute(stmt)
    return [_to_read(a) for a in result.scalars().all()]


@router.get("/service/{service_id}", response_model=list[AttendanceRead])
async def get_service_attendance(
    service_id: UUIDType,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attendance for every member who attended a specific service.

    Cached in Redis for 30s and invalidated on new check-ins for the service.
    """
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")

    cache_key = _service_cache_key(service_id)
    cached = await cache_get_json(cache_key)
    if cached is not None:
        return cached

    stmt = (
        select(Attendance)
        .options(*_ATTENDANCE_EAGER)
        .where(Attendance.service_id == service_id)
        .order_by(Attendance.check_in_time.desc())
    )
    result = await db.execute(stmt)
    records = [_to_read(a) for a in result.scalars().all()]

    payload = [r.model_dump(mode="json") for r in records]
    await cache_set_json(cache_key, payload, ttl=30)
    return payload