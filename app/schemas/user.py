from pydantic import BaseModel, ConfigDict, EmailStr
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.enums import RoleEnum, GroupMembershipStatus
from typing import List, Optional

class ProfileRead(BaseModel):
    id: UUID
    first_name: Optional[str]
    last_name: Optional[str]
    phone_number: Optional[str]
    role: RoleEnum
    
    model_config = ConfigDict(from_attributes=True)

class UserRead(BaseModel):
    id: UUID
    email: EmailStr
    is_active: bool
    profile: ProfileRead
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class UserAdminOverview(BaseModel):
    id: str
    fullname: str
    email: Optional[str]
    department: Optional[str]
    group_name: Optional[str]
    membership_status: Optional[GroupMembershipStatus]
    role: Optional[RoleEnum]

    class Config:
        model_config = ConfigDict(from_attributes=True)

class UserMinimal(BaseModel):
    id: str
    fullname: str

    class Config:
        model_config = ConfigDict(from_attributes=True)