from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.session import Session as AuthSession

from sqlalchemy.orm import selectinload

async def get_current_user(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
):

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
    async def checker(user: User = Depends(get_current_user)):
        if user.role != required:
            raise HTTPException(status_code=403, detail="Forbidden")
        return user

    return checker