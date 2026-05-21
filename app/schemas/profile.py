from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional
from uuid import UUID
from datetime import date, datetime
from app.models.enums import RoleEnum, MaritalStatus, Group, GroupMembershipStatus


# -----------------------------
# BASE
# -----------------------------

class ProfileBase(BaseModel):
    fullname: Optional[str] = Field(None, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    dob: Optional[date] = None
    marital_status: Optional[MaritalStatus] = None
    address: Optional[str] = Field(None, max_length=255)
    emergency_contact: Optional[str] = Field(None, max_length=20)
    emergency_name: Optional[str] = Field(None, max_length=50)
    department: Optional[str] = Field(None, max_length=50)
    fingerprint_id: Optional[str] = Field(None, max_length=50)


# -----------------------------
# CREATE (First login sync)
# -----------------------------

class ProfileCreate(BaseModel):
    user_id: str
    fullname: Optional[str] = None
    email: str  # From BetterAuth


# -----------------------------
# UPDATE (User completes profile)
# -----------------------------

class ProfileUpdate(ProfileBase):
    pass


# -----------------------------
# ADMIN ROLE UPDATE
# -----------------------------

class ProfileRoleUpdate(BaseModel):
    """Sent by SUPER_ADMIN to set a profile's roles. Backend will
    always ensure RoleEnum.USER is present in the resulting list."""
    roles: List[RoleEnum] = Field(default_factory=list)


class ProfileFingerprintUpdate(BaseModel):
    fingerprint_id: Optional[str] = Field(None, max_length=50)


# -----------------------------
# RESPONSE
# -----------------------------

class ProfileRead(ProfileBase):
    id: UUID
    user_id: str
    roles: List[RoleEnum]
    profile_completed: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

