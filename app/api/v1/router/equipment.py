from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.models.equipment import Equipment
from app.schemas.equipment import EquipmentCreate, EquipmentUpdate, EquipmentRead

router = APIRouter(prefix="/equipment", tags=["Equipments"])


@router.get("", response_model=list[EquipmentRead])
async def get_equipments(db: AsyncSession = Depends(get_db)):
    stmt = select(Equipment)
    result = await db.execute(stmt)
    equipments = result.scalars().all()
    return equipments


@router.post("", response_model=EquipmentRead)
async def create_equipment(
    payload: EquipmentCreate,
    db: AsyncSession = Depends(get_db),
):
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

    return equipment


@router.patch("/{equipment_id}", response_model=EquipmentRead)
async def update_equipment(
    equipment_id: str,
    payload: EquipmentUpdate,
    db: AsyncSession = Depends(get_db),
):
    equipment = await db.get(Equipment, equipment_id)
    if not equipment:
        raise HTTPException(404, "Equipment not found")

    # Only update provided fields
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(equipment, field, value)

    await db.commit()
    await db.refresh(equipment)

    return equipment


@router.delete("/{equipment_id}")
async def delete_equipment(
    equipment_id: str,
    db: AsyncSession = Depends(get_db),
):
    equipment = await db.get(Equipment, equipment_id)
    if not equipment:
        raise HTTPException(404, "Equipment not found")

    await db.delete(equipment)
    await db.commit()

    return {"message": "Equipment deleted successfully"}