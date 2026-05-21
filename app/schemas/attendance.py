from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime, date


class AttendanceRead(BaseModel):
    id: UUID
    profile_id: UUID
    user_id: str
    member_name: str | None
    service_id: UUID
    service_date: date
    check_in_time: datetime

    model_config = ConfigDict(from_attributes=True)
