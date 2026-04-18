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
)

router = APIRouter(prefix="/profiles", tags=["Profiles"])


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
):
    stmt = select(Profile).where(Profile.user_id == user_id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile.role = payload.role

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
):
    stmt = select(Profile).where(Profile.user_id == user_id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    await db.delete(profile)
    await db.commit()

    return