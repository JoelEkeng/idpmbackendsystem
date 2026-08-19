from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class VisitorCreate(BaseModel):
    """Public registration payload. No user_id/roles/id fields — this can
    never create or touch a CMS account."""

    full_name: str = Field(..., min_length=2, max_length=255)
    phone_number: str = Field(..., min_length=7, max_length=20)
    email: EmailStr | None = None
    gender: str | None = Field(None, max_length=10)
    programme: str = Field(..., min_length=2, max_length=150)
    visit_date: date | None = None  # defaults to today server-side if omitted
    notes: str | None = Field(None, max_length=500)

    @field_validator("phone_number")
    @classmethod
    def _strip_phone(cls, v: str) -> str:
        return v.strip()


class VisitorRead(BaseModel):
    id: UUID
    full_name: str
    phone_number: str
    email: str | None
    gender: str | None
    programme: str
    visit_date: date
    notes: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
