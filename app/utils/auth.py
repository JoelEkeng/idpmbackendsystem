from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.session import Session as AuthSession

from sqlalchemy.orm import selectinload

async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth header")

    session_token = authorization.replace("Bearer ", "")

    result = await db.execute(
        select(AuthSession).where(AuthSession.token == session_token)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    result = await db.execute(
        select(User)
        .options(selectinload(User.profile))  # loads profile
        .where(User.id == session.userId)
    )

    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user

def require_role(required: str):
    """Legacy compatibility shim. Prefer `app.utils.permissions.require_roles`."""
    from app.models.enums import RoleEnum
    from app.utils.permissions import require_roles

    try:
        role = RoleEnum(required)
    except ValueError as exc:
        raise ValueError(f"Unknown role: {required!r}") from exc
    return require_roles(role)