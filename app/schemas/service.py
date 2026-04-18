from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import date, datetime, time


class ServiceBase(BaseModel):
    date: date
    start_time: time
    end_time: time
    grace_before_minutes: int = 30
    grace_after_minutes: int = 15


class ServiceCreate(ServiceBase):
    pass


class ServiceRead(ServiceBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)