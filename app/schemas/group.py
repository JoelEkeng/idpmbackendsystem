from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from app.models.enums import GroupMembershipStatus

class LeaderInfo(BaseModel):
    id: str
    name: str | None

    model_config = {"from_attributes": True}

class GroupRequest(BaseModel):
    group_id: UUID


class GroupApproval(BaseModel):
    status: GroupMembershipStatus 


class GroupMemberRead(BaseModel):
    id: UUID
    user_id: str
    group_id: UUID
    status: GroupMembershipStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class GroupCreate(BaseModel):
    name: str
    leader_id: str | None = None

class GroupRead(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    leader: LeaderInfo | None
    member_count: int

    model_config = {"from_attributes": True}