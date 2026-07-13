from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.cache import cache_get_json, cache_set_json, cache_delete
from app.models.service import Service
from app.schemas.service import ServiceCreate, ServiceRead
from uuid import UUID
from app.models.user import User
from app.models.enums import RoleEnum
from fastapi import Depends
from app.utils.auth import get_current_user
from app.utils.permissions import is_admin

router = APIRouter(prefix="/services", tags=["Services"])

_SERVICES_CACHE_KEY = "services:all"
_SERVICES_CACHE_TTL = 60  # seconds; services change rarely


@router.get("", response_model=list[ServiceRead])
async def get_services(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List services (any authenticated user). Cached in Redis for 60s."""
    cached = await cache_get_json(_SERVICES_CACHE_KEY)
    if cached is not None:
        return cached

    stmt = select(Service).order_by(Service.date.desc())
    result = await db.execute(stmt)
    services = result.scalars().all()

    payload = [ServiceRead.model_validate(s).model_dump(mode="json") for s in services]
    await cache_set_json(_SERVICES_CACHE_KEY, payload, ttl=_SERVICES_CACHE_TTL)
    return payload


@router.post("", response_model=ServiceRead, status_code=201)
async def create_service(
    payload: ServiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin-only: create a service."""
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")
        
    service = Service(**payload.model_dump())

    db.add(service)
    await db.commit()
    await db.refresh(service)

    await cache_delete(_SERVICES_CACHE_KEY)
    return service

@router.patch("/{service_id}", response_model=ServiceRead)
async def update_service(
    service_id: UUID,
    payload: ServiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin-only: update a service."""
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")

    stmt = select(Service).where(Service.id == service_id)
    result = await db.execute(stmt)
    service = result.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    for key, value in payload.model_dump().items():
        setattr(service, key, value)
    await db.commit()
    await db.refresh(service)

    await cache_delete(_SERVICES_CACHE_KEY)
    return service

@router.delete("/{service_id}", status_code=200)
async def delete_service(
    service_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin-only: delete a service."""
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")
        
    stmt = select(Service).where(Service.id == service_id)
    result = await db.execute(stmt)
    service = result.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    await db.delete(service)
    await db.commit()

    await cache_delete(_SERVICES_CACHE_KEY)
    return {"message": "Service deleted successfully"}