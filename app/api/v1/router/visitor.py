"""Visitor / programme-attendance registration.

Deliberately separate from the CMS member flow: registering here never
creates a `User`/`Profile`, issues no session, and grants no CMS access.
Listing/exporting visitor records is admin-only.
"""

from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.visitor import Visitor
from app.schemas.visitor import VisitorCreate, VisitorRead
from app.utils.auth import get_current_user
from app.utils.permissions import is_admin

router = APIRouter(prefix="/visitors", tags=["Visitors"])


@router.post("", response_model=VisitorRead, status_code=201)
async def register_visitor(
    payload: VisitorCreate,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint: anyone attending a programme can register here
    without an account. Subject to the app's global rate limiting."""
    visitor = Visitor(
        full_name=payload.full_name.strip(),
        phone_number=payload.phone_number,
        email=payload.email,
        gender=payload.gender,
        programme=payload.programme.strip(),
        visit_date=payload.visit_date or date_type.today(),
        notes=payload.notes,
    )
    db.add(visitor)
    await db.commit()
    await db.refresh(visitor)
    return visitor


@router.get("", response_model=list[VisitorRead])
async def list_visitors(
    programme: str | None = Query(None),
    from_date: date_type | None = Query(None),
    to_date: date_type | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin-only: browse visitor/programme-attendance records."""
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")

    stmt = select(Visitor)
    if programme:
        stmt = stmt.where(Visitor.programme == programme)
    if from_date:
        stmt = stmt.where(Visitor.visit_date >= from_date)
    if to_date:
        stmt = stmt.where(Visitor.visit_date <= to_date)

    stmt = stmt.order_by(Visitor.visit_date.desc(), Visitor.created_at.desc())
    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/count")
async def count_visitors(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin-only: cheap total count for dashboard cards (no need to fetch rows)."""
    if not is_admin(current_user):
        raise HTTPException(403, "Admins only")

    total = await db.scalar(select(func.count()).select_from(Visitor))
    return {"total_visitors": total or 0}
