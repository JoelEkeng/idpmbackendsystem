from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.cache import cache_get_json, cache_set_json, cache_delete_prefix
from app.models.equipment import Equipment
from app.models.user import User
from app.models.enums import RoleEnum
from app.schemas.equipment import EquipmentCreate, EquipmentUpdate, EquipmentRead
from app.utils.auth import get_current_user
from app.utils.permissions import is_admin

router = APIRouter(prefix="/equipment", tags=["Equipments"])

_EQUIPMENT_CACHE_PREFIX = "equipment:list:"
_EQUIPMENT_CACHE_TTL = 300  # equipment changes rarely


def _equipment_cache_key(limit: int, offset: int) -> str:
    return f"{_EQUIPMENT_CACHE_PREFIX}{limit}:{offset}"


@router.get("", response_model=list[EquipmentRead])
async def get_equipments(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")

    cache_key = _equipment_cache_key(limit, offset)
    cached = await cache_get_json(cache_key)
    if cached is not None:
        return cached

    stmt = select(Equipment).limit(limit).offset(offset)
    result = await db.execute(stmt)
    equipments = result.scalars().all()

    payload = [EquipmentRead.model_validate(e).model_dump(mode="json") for e in equipments]
    await cache_set_json(cache_key, payload, ttl=_EQUIPMENT_CACHE_TTL)
    return payload


@router.post("", response_model=EquipmentRead)
async def create_equipment(
    payload: EquipmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")

    # Check uniqueness of ID
    existing = await db.get(Equipment, payload.id)
    if existing:
        raise HTTPException(400, "Equipment ID already exists")

    equipment = Equipment(
        id=payload.id,
        name=payload.name,
        quantity=payload.quantity,
        state=payload.state,
        category=payload.category,
        location=payload.location,
    )

    db.add(equipment)
    await db.commit()
    await db.refresh(equipment)

    await cache_delete_prefix(_EQUIPMENT_CACHE_PREFIX)
    return equipment


@router.patch("/{equipment_id}", response_model=EquipmentRead)
async def update_equipment(
    equipment_id: str,
    payload: EquipmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")

    equipment = await db.get(Equipment, equipment_id)
    if not equipment:
        raise HTTPException(404, "Equipment not found")

    # Only update provided fields
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(equipment, field, value)

    await db.commit()
    await db.refresh(equipment)

    await cache_delete_prefix(_EQUIPMENT_CACHE_PREFIX)
    return equipment


@router.delete("/{equipment_id}")
async def delete_equipment(
    equipment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")

    equipment = await db.get(Equipment, equipment_id)
    if not equipment:
        raise HTTPException(404, "Equipment not found")

    await db.delete(equipment)
    await db.commit()

    await cache_delete_prefix(_EQUIPMENT_CACHE_PREFIX)
    return {"message": "Equipment deleted successfully"}