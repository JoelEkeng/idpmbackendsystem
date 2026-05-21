from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.profile import Profile
from app.models.user import User
from app.schemas.profile import (
    ProfileCreate,
    ProfileUpdate,
    ProfileRead,
    ProfileRoleUpdate,
    ProfileFingerprintUpdate,
)
from app.utils.auth import get_current_user
from app.utils.permissions import is_admin, is_super_admin
from app.models.enums import RoleEnum

router = APIRouter(prefix="/profiles", tags=["Profiles"])


# ---------------------------------------------------------
# 0️⃣ SYNC PROFILE (First sign-in bootstrap)
# Idempotent: ensures a Profile row exists for the authed
# BetterAuth user. Safe to call on every sign-in.
# ---------------------------------------------------------

@router.post("/sync", response_model=ProfileRead)
async def sync_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Profile).where(Profile.user_id == current_user.id)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        return existing

    profile = Profile(
        user_id=current_user.id,
        fullname=current_user.name,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.post("", response_model=ProfileRead)
async def create_profile( 
    payload: ProfileCreate,
    db: AsyncSession = Depends(get_db),
):
    # Ensure user exists in BetterAuth user table mirror
    stmt = select(User).where(User.id == payload.user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if profile already exists
    stmt = select(Profile).where(Profile.user_id == payload.user_id)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        return existing

    profile = Profile(
        user_id=payload.user_id,
        fullname=payload.fullname,
    )

    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    return profile


@router.patch("/{user_id}/fingerprint", response_model=ProfileRead)
async def update_fingerprint_id(
    user_id: str,
    payload: ProfileFingerprintUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")

    stmt = select(Profile).where(Profile.user_id == user_id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    fingerprint_id = payload.fingerprint_id.strip() if payload.fingerprint_id else None
    if fingerprint_id:
        existing_stmt = select(Profile).where(
            Profile.fingerprint_id == fingerprint_id,
            Profile.user_id != user_id,
        )
        existing_result = await db.execute(existing_stmt)
        existing_profile = existing_result.scalar_one_or_none()
        if existing_profile:
            raise HTTPException(status_code=400, detail="Fingerprint ID already in use")

    profile.fingerprint_id = fingerprint_id

    await db.commit()
    await db.refresh(profile)

    return profile


# ---------------------------------------------------------
# 2️⃣ GET PROFILE (Current User)
# ---------------------------------------------------------

@router.get("/{user_id}", response_model=ProfileRead)
async def get_profile(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Profile).where(Profile.user_id == user_id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    return profile


# ---------------------------------------------------------
# 3️⃣ UPDATE PROFILE (User completes profile)
# ---------------------------------------------------------

@router.patch("/{user_id}", response_model=ProfileRead)
async def update_profile(
    user_id: str,
    payload: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Profile).where(Profile.user_id == user_id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    update_data = payload.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(profile, field, value)

    # Check completion logic
    required_fields = [
        profile.fullname,
        profile.phone_number,
        profile.dob,
        profile.address,
    ]

    if all(required_fields):
        profile.profile_completed = True

    await db.commit()
    await db.refresh(profile)

    return profile


# ---------------------------------------------------------
# 4️⃣ ADMIN ROLE UPDATE
# ---------------------------------------------------------

@router.patch("/{user_id}/role", response_model=ProfileRead)
async def update_role(
    user_id: str,
    payload: ProfileRoleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Only SUPER_ADMIN can mutate roles — ADMIN should not be able to escalate.
    if not is_super_admin(current_user):
        raise HTTPException(403, "Super admin only")

    stmt = select(Profile).where(Profile.user_id == user_id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Apply roles from payload (always include USER as the base).
    incoming = list(payload.roles or [])
    if RoleEnum.USER not in incoming:
        incoming.insert(0, RoleEnum.USER)
    # Only one SUPER_ADMIN allowed in the system.
    if RoleEnum.SUPER_ADMIN in incoming:
        existing_q = await db.execute(
            select(Profile).where(
                Profile.roles.any(RoleEnum.SUPER_ADMIN),
                Profile.user_id != user_id,
            )
        )
        if existing_q.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=400,
                detail="There can only be one SUPER_ADMIN in the system.",
            )
    profile.roles = incoming

    await db.commit()
    await db.refresh(profile)

    return profile


# ---------------------------------------------------------
# 5️⃣ DELETE PROFILE
# ---------------------------------------------------------

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")

    stmt = select(Profile).where(Profile.user_id == user_id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    await db.delete(profile)
    await db.commit()

    return