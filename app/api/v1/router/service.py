from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.models.service import Service
from app.schemas.service import ServiceCreate, ServiceRead

router = APIRouter(prefix="/services", tags=["Services"])


@router.get("", response_model=list[ServiceRead])
async def get_services(db: AsyncSession = Depends(get_db)):
    stmt = select(Service).order_by(Service.date.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=ServiceRead, status_code=201)
async def create_service(
    payload: ServiceCreate,
    db: AsyncSession = Depends(get_db),
):
    service = Service(**payload.model_dump())

    db.add(service)
    await db.commit()
    await db.refresh(service)

    return service