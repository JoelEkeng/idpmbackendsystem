from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID
from app.core.database import get_db
from app.core.cache import cache_get_json, cache_set_json, cache_delete
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

_GROUPS_CACHE_KEY = "groups:all"
_GROUPS_CACHE_TTL = 300  # groups/leaders/member counts change rarely


@router.get("", response_model=list[GroupRead])
async def get_groups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not (current_user.profile):
        raise HTTPException(403, "Only users are allowed")

    cached = await cache_get_json(_GROUPS_CACHE_KEY)
    if cached is not None:
        return cached

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

    payload = [
        GroupRead.model_validate(
            {
                "id": group.id,
                "name": group.name,
                "created_at": group.created_at,
                "leader": group.leader,
                "member_count": count,
            }
        ).model_dump(mode="json")
        for group, count in rows
    ]
    await cache_set_json(_GROUPS_CACHE_KEY, payload, ttl=_GROUPS_CACHE_TTL)
    return payload

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
    await cache_delete(_GROUPS_CACHE_KEY)

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
    await cache_delete(_GROUPS_CACHE_KEY)

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
    await cache_delete(_GROUPS_CACHE_KEY)

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
        if existing.status in (
            GroupMembershipStatus.PENDING,
            GroupMembershipStatus.LEADER_APPROVED,
        ):
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
    """Stage 1: the group leader recommends a PENDING request.

    This does NOT make the user a member yet — it only moves the request to
    LEADER_APPROVED, awaiting admin final approval (see `/approve-final`).
    """
    membership = await db.get(GroupMember, membership_id)
    if not membership:
        raise HTTPException(404, "Membership not found")

    group = await db.get(Group, membership.group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    if group.leader_id != current_user.id:
        raise HTTPException(403, "Only the group leader can approve members")

    # A leader cannot approve their own membership request into their own group.
    if membership.user_id == current_user.id:
        raise HTTPException(403, "You cannot approve your own membership request")

    if membership.status != GroupMembershipStatus.PENDING:
        raise HTTPException(400, "Only pending requests can be approved by the leader")

    membership.status = GroupMembershipStatus.LEADER_APPROVED
    membership.approved_by = current_user.id

    await db.commit()
    await db.refresh(membership)

    return membership


@router.post("/{membership_id}/approve-final", response_model=GroupMemberRead)
async def admin_approve_group_member(
    membership_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stage 2: admin gives final approval to a leader-recommended request,
    turning it into an actual approved membership."""
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")

    membership = await db.get(GroupMember, membership_id)
    if not membership:
        raise HTTPException(404, "Membership not found")

    if membership.status != GroupMembershipStatus.LEADER_APPROVED:
        raise HTTPException(
            400, "Only leader-approved requests can receive final admin approval"
        )

    # An admin cannot approve their own membership request.
    if membership.user_id == current_user.id:
        raise HTTPException(403, "You cannot approve your own membership request")

    membership.status = GroupMembershipStatus.APPROVED
    membership.approved_by = current_user.id

    await db.commit()
    await db.refresh(membership)
    await cache_delete(_GROUPS_CACHE_KEY)

    return membership


@router.get("/admin/leader-approved", response_model=list[GroupMemberRead])
async def list_leader_approved_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin-only: requests a group leader has recommended, awaiting final
    admin approval."""
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")

    stmt = select(GroupMember).where(
        GroupMember.status == GroupMembershipStatus.LEADER_APPROVED
    )
    result = await db.execute(stmt)
    return result.scalars().unique().all()


@router.post("/{membership_id}/reject", response_model=GroupMemberRead)
async def reject_group_member(
    membership_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reject a request. The group leader can reject a PENDING request for
    their own group; an admin can reject a PENDING or LEADER_APPROVED request
    for any group (e.g. overriding a leader's recommendation)."""
    membership = await db.get(GroupMember, membership_id)
    if not membership:
        raise HTTPException(404, "Membership not found")

    group = await db.get(Group, membership.group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    admin = is_admin(current_user)
    is_leader = group.leader_id == current_user.id

    if not (admin or is_leader):
        raise HTTPException(403, "Only the group leader or an admin can reject members")

    if is_leader and not admin and membership.status != GroupMembershipStatus.PENDING:
        raise HTTPException(400, "Leaders can only reject pending requests")

    if membership.status not in (
        GroupMembershipStatus.PENDING,
        GroupMembershipStatus.LEADER_APPROVED,
    ):
        raise HTTPException(400, "This request has already been finalized")

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