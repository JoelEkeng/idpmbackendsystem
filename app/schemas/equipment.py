from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class EquipmentBase(BaseModel):
    name: str
    quantity: int
    state: str
    category: Optional[str] = None
    location: Optional[str] = None

class EquipmentCreate(EquipmentBase):
    id: str

class EquipmentUpdate(BaseModel):
    name: Optional[str] = None
    quantity: Optional[int] = None
    state: Optional[str] = None
    category: Optional[str] = None
    location: Optional[str] = None

class EquipmentRead(EquipmentBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)