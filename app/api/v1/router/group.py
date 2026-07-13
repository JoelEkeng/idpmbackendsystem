from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
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
from app.utils.auth import get_current_user
from app.utils.permissions import is_admin
from app.models.enums import RoleEnum

router = APIRouter(prefix="/groups", tags=["Group"])

@router.get("", response_model=list[GroupRead])
async def get_groups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not (current_user.profile):
        raise HTTPException(403, "Only users are allowed")

    # Count members per group with a single aggregate instead of loading every
    # GroupMember row into memory just to call len().
    member_counts = (
        select(GroupMember.group_id, func.count(GroupMember.id).label("member_count"))
        .group_by(GroupMember.group_id)
        .subquery()
    )

    stmt = (
        select(Group, func.coalesce(member_counts.c.member_count, 0))
        .outerjoin(member_counts, Group.id == member_counts.c.group_id)
        .options(selectinload(Group.leader))
    )

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "id": group.id,
            "name": group.name,
            "created_at": group.created_at,
            "leader": group.leader,
            "member_count": count,
        }
        for group, count in rows
    ]

@router.post("", response_model=GroupRead)
async def create_group(
    payload: GroupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")
        
    # If leader_id provided, ensure user exists
    if payload.leader_id:
        leader = await db.get(User, payload.leader_id)
        if not leader:
            raise HTTPException(404, "Leader not found")
    
    group = Group(
        name=payload.name,
        # leader_id=payload.leader_id,
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

@router.patch("/{group_id}", response_model=GroupRead)
async def update_group(
    group_id: UUID,
    payload: GroupCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")
        
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    if payload.leader_id:
        leader = await db.get(User, payload.leader_id)
        if not leader:
            raise HTTPException(404, "Leader not found")
    
        if current_user.id not in [member.user_id for member in group.members]:
            raise HTTPException(400, "User is not a member of this group")
        
        if payload.leader_id == current_user.id:
            raise HTTPException(400, "You cannot assign yourself as leader")

    group.name = payload.name

    group.leader_id = payload.leader_id

    await db.commit()
    await db.refresh(group)

    return group


@router.delete("/{group_id}")
async def delete_group(
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")
        
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    await db.delete(group)
    await db.commit()

    return {"message": "Group deleted successfully"}


@router.post("/request", response_model=GroupMemberRead)
async def request_group_membership(
    payload: GroupRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = await db.get(Group, payload.group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    # Only one group allowed per user. Re-requesting after rejection
    # should replace the prior record to keep the unique constraint happy.
    result = await db.execute(
        select(GroupMember).where(GroupMember.user_id == current_user.id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        if existing.status == GroupMembershipStatus.APPROVED:
            raise HTTPException(400, "User already belongs to a group")
        if existing.status == GroupMembershipStatus.PENDING:
            raise HTTPException(400, "A pending request already exists")
        # REJECTED → allow re-request by replacing
        await db.delete(existing)
        await db.flush()

    membership = GroupMember(
        user_id=current_user.id,
        group_id=payload.group_id,
        status=GroupMembershipStatus.PENDING,
    )

    db.add(membership)
    await db.commit()
    await db.refresh(membership)

    return membership


@router.get("/leader/pending", response_model=list[GroupMemberRead])
async def list_pending_requests_for_leader(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return PENDING memberships for groups led by the current user."""
    stmt = (
        select(GroupMember)
        .join(Group, GroupMember.group_id == Group.id)
        .where(
            Group.leader_id == current_user.id,
            GroupMember.status == GroupMembershipStatus.PENDING,
        )
    )
    result = await db.execute(stmt)
    return result.scalars().unique().all()


@router.post("/{membership_id}/approve", response_model=GroupMemberRead)
async def approve_group_member(
    membership_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    membership = await db.get(GroupMember, membership_id)
    if not membership:
        raise HTTPException(404, "Membership not found")

    group = await db.get(Group, membership.group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    if group.leader_id != current_user.id:
        raise HTTPException(403, "Only the group leader can approve members")

    membership.status = GroupMembershipStatus.APPROVED
    membership.approved_by = current_user.id

    await db.commit()
    await db.refresh(membership)

    return membership


@router.post("/{membership_id}/reject", response_model=GroupMemberRead)
async def reject_group_member(
    membership_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    membership = await db.get(GroupMember, membership_id)
    if not membership:
        raise HTTPException(404, "Membership not found")

    group = await db.get(Group, membership.group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    if group.leader_id != current_user.id:
        raise HTTPException(403, "Only the group leader can reject members")

    membership.status = GroupMembershipStatus.REJECTED
    membership.approved_by = current_user.id

    await db.commit()
    await db.refresh(membership)

    return membership

@router.get("/{group_id}/members", response_model=list[GroupMemberRead])
async def get_group_members(
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = await db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    if group.leader_id != current_user.id and not is_admin(current_user):
        raise HTTPException(403, "Only the group leader or an admin can view members")

    result = await db.execute(
        select(GroupMember).where(GroupMember.group_id == group_id)
    )

    return result.scalars().all()