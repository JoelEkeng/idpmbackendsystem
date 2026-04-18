from pydantic import BaseModel
from uuid import UUID
from app.schemas.profile import ProfileRead
from app.models.enums import GroupMembershipStatus

class LeaderRead(BaseModel):
    id: str
    name: str | None

    model_config = {"from_attributes": True}


class GroupWithLeaderRead(BaseModel):
    id: UUID
    name: str
    leader: LeaderRead | None

    model_config = {"from_attributes": True}


class GroupWithMembershipRead(BaseModel):
    id: UUID
    name: str
    membership_status: GroupMembershipStatus
    leader: LeaderRead | None

    model_config = {"from_attributes": True}


class UserOverview(BaseModel):
    profile: ProfileRead | None
    group: GroupWithLeaderRead | None
    group: GroupWithMembershipRead | None

    model_config = {"from_attributes": True}