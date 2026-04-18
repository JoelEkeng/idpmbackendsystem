from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.core.database import get_db
from app.models.user import User
from app.models.group import Group, GroupMember
from app.models.enums import GroupMembershipStatus
from app.schemas.group import (
    GroupRequest,
    GroupMemberRead,
    GroupCreate,
    GroupRead,
)
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/groups", tags=["Group"])

# @router.get("/", response_model=list[GroupRead])
# async def get_groups(
#     db: AsyncSession = Depends(get_db),
# ):
#     result = await db.execute(select(Group))
#     groups = result.scalars().all()
#     return [GroupRead.model_validate(group) for group in groups]    
    
#     return groups

@router.get("", response_model=list[GroupRead])
async def get_groups(
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Group)
        .options(
            selectinload(Group.leader),
            selectinload(Group.members)  # assuming relationship exists
        )
    )

    result = await db.execute(stmt)
    groups = result.scalars().unique().all()

    response = []

    for group in groups:
        response.append({
            "id": group.id,
            "name": group.name,
            "created_at": group.created_at,
            "leader": group.leader,
            "member_count": len(group.members),
        })

    return response

@router.post("", response_model=GroupRead)
async def create_group(
    payload: GroupCreate,
    db: AsyncSession = Depends(get_db),
):
    # If leader_id provided, ensure user exists
    if payload.leader_id:
        leader = await db.get(User, payload.leader_id)
        if not leader:
            raise HTTPException(404, "Leader not found")

    group = Group(
        name=payload.name,
        leader_id=payload.leader_id,
    )

    db.add(group)
    await db.commit()
    await db.refresh(group)

    # Build response object for GroupRead
    response_data = GroupRead.model_validate({
        "id": group.id,
        "name": group.name,
        "created_at": group.created_at,
        "leader": group.leader,           # assuming nested leader serialization works
        "member_count": len(group.members)  # This ensures member_count exists
    })

    return response_data

@router.patch("/{group_id}/assign-leader", response_model=GroupRead)
async def assign_group_leader(
    group_id: UUID,
    leader_id: str,
    db: AsyncSession = Depends(get_db),
):
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    leader = await db.get(User, leader_id)
    if not leader:
        raise HTTPException(404, "User not found")

    group.leader_id = leader_id

    await db.commit()
    await db.refresh(group)

    return group

@router.patch("/{group_id}", response_model=GroupRead)
async def update_group(
    group_id: UUID,
    payload: GroupCreate,
    db: AsyncSession = Depends(get_db),
):
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    if payload.leader_id:
        leader = await db.get(User, payload.leader_id)
        if not leader:
            raise HTTPException(404, "Leader not found")

    group.name = payload.name

    group.leader_id = payload.leader_id

    await db.commit()
    await db.refresh(group)

    return group


@router.delete("/{group_id}")
async def delete_group(
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    await db.delete(group)
    await db.commit()

    return {"message": "Group deleted successfully"}


@router.post("/request", response_model=GroupMemberRead)
async def request_group_membership(
    user_id: str,
    payload: GroupRequest,
    db: AsyncSession = Depends(get_db),
):
    group = await db.get(Group, payload.group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    # Only one group allowed per user (your constraint enforces this)
    result = await db.execute(
        select(GroupMember).where(GroupMember.user_id == user_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(400, "User already has a group membership")

    membership = GroupMember(
        user_id=user_id,
        group_id=payload.group_id,
        status=GroupMembershipStatus.PENDING,
    )

    db.add(membership)
    await db.commit()
    await db.refresh(membership)

    return membership

@router.post("/{membership_id}/approve", response_model=GroupMemberRead)
async def approve_group_member(
    membership_id: UUID,
    approver_id: str,
    db: AsyncSession = Depends(get_db),
):
    membership = await db.get(GroupMember, membership_id)
    if not membership:
        raise HTTPException(404, "Membership not found")

    approver = await db.get(User, approver_id)
    if not approver:
        raise HTTPException(404, "Approver not found")

    membership.status = GroupMembershipStatus.APPROVED
    membership.approved_by = approver_id

    await db.commit()
    await db.refresh(membership)

    return membership

@router.get("/{group_id}/members", response_model=list[GroupMemberRead])
async def get_group_members(
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    result = await db.execute(
        select(GroupMember).where(GroupMember.group_id == group_id)
    )

    return result.scalars().all()