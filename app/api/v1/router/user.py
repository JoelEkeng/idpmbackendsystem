from sqlalchemy.orm import selectinload
from app.schemas.profile import ProfileRead
from app.schemas.group import GroupRead
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.models.user import User
from app.models.group import GroupMember, Group
from app.schemas.useroverview import UserOverview, GroupWithMembershipRead
from app.schemas.user import UserAdminOverview, UserMinimal

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/{user_id}/overview", response_model=UserOverview)
async def get_user_overview(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.profile),
            selectinload(User.memberships)
            .selectinload(GroupMember.group)
            .selectinload(Group.leader)
        )
    )

    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(404, "User not found")

    # Because you allow only one group
    membership = user.memberships[0] if user.memberships else None
    if membership:
        group_data = {
            "id": membership.group.id,
            "name": membership.group.name,
            # "description": membership.group.description,
            "membership_status": membership.status,
            "leader": membership.group.leader,
        }
    else:
        group_data = None

    return {
        "profile": user.profile,
        "group": group_data,
        
    }



# This is commented out for security reasons and to reduce fetching all the user data at once to the frontend.

# @router.get("", response_model=list[UserOverview])
# async def get_users(
#     db: AsyncSession = Depends(get_db),
# ):
#     stmt = (
#         select(User)
#         .options(
#             selectinload(User.profile),
#             selectinload(User.memberships)
#             .selectinload(GroupMember.group)
#             .selectinload(Group.leader)
#         )
#     )

#     result = await db.execute(stmt)
#     users = result.scalars().unique().all()

#     response = []

#     for user in users:
#         membership = user.memberships[0] if user.memberships else None

#         if membership:
#             group_data = {
#                 "id": membership.group.id,
#                 "name": membership.group.name,
#                 "membership_status": membership.status,
#                 "leader": membership.group.leader,
#             }
#         else:
#             group_data = None

#         response.append({
#             "profile": user.profile,
#             "group": group_data,
#         })

#     return response



@router.get("/minimal", response_model=list[UserMinimal])
async def get_minimal_users(db: AsyncSession = Depends(get_db)):
    # Select only the columns we need
    stmt = select(User.id, User.name, User.email)
    result = await db.execute(stmt)
    
    # Map to list of UserMinimal
    users = result.all()  # returns list of tuples (id, full_name)
    return [UserMinimal(id=u.id, fullname=u.name, email=u.email) for u in users]

@router.get("/{user_id}/minimal", response_model=UserMinimal)
async def get_minimal_user(user_id: str, db: AsyncSession = Depends(get_db)):
    # Select only the columns we need
    stmt = select(User.id, User.name).where(User.id == user_id)
    result = await db.execute(stmt)
    
    user = result.fetchone()
    if not user:
        raise HTTPException(404, "User not found")

    return UserMinimal(id=user.id, fullname=user.name)
    # Map to list of UserMinimal
    users = result.all()  # returns list of tuples (id, full_name)
    return [UserMinimal(id=u.id, fullname=u.name) for u in users]



@router.get("/admin-overview", response_model=list[UserAdminOverview])
async def get_users_for_admin(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(User)
        .options(
            selectinload(User.profile),
            selectinload(User.memberships)
            .selectinload(GroupMember.group)
        )
    )
    result = await db.execute(stmt)
    users = result.scalars().unique().all()

    response = []
    for user in users:
        membership = user.memberships[0] if user.memberships else None
        response.append(
            UserAdminOverview(
                id=user.id,
                fullname=user.profile.fullname if user.profile else user.name,
                email=user.email if user.profile else None,
                department=user.profile.department if user.profile else None,
                group_name=membership.group.name if membership else None,
                membership_status=membership.status if membership else None,
                role=user.profile.role if user.profile else None
            )
        )
    return response