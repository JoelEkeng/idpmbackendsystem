"""Centralized authorization helpers.

Roles are stored as an ARRAY on `Profile.roles`. A user always has at least
`RoleEnum.USER`; extra roles are appended (e.g. `[USER, GROUP_LEADER]`).

These helpers raise `HTTPException(403)` when the requirement isn't met,
so they're safe to call directly inside route handlers.
"""

from typing import Iterable

from fastapi import Depends, HTTPException

from app.models.enums import RoleEnum
from app.models.user import User
from app.utils.auth import get_current_user


def user_roles(user: User) -> list[RoleEnum]:
    """Return the user's roles as a list of `RoleEnum`. Empty list if no profile."""
    profile = getattr(user, "profile", None)
    if not profile or not getattr(profile, "roles", None):
        return []
    out: list[RoleEnum] = []
    for r in profile.roles:
        if isinstance(r, RoleEnum):
            out.append(r)
        else:
            try:
                out.append(RoleEnum(r))
            except ValueError:
                continue
    return out


def has_any_role(user: User, *required: RoleEnum) -> bool:
    """True if the user has at least one of the given roles."""
    if not required:
        return True
    have = set(user_roles(user))
    return bool(have.intersection(required))


def is_admin(user: User) -> bool:
    """ADMIN or SUPER_ADMIN."""
    return has_any_role(user, RoleEnum.ADMIN, RoleEnum.SUPER_ADMIN)


def is_super_admin(user: User) -> bool:
    return has_any_role(user, RoleEnum.SUPER_ADMIN)


def require_roles(*required: RoleEnum):
    """Dependency factory: raises 403 unless the current user has any of the required roles."""

    async def _checker(user: User = Depends(get_current_user)) -> User:
        if not has_any_role(user, *required):
            raise HTTPException(status_code=403, detail="Forbidden")
        return user

    return _checker


def require_admin():
    """Dependency: ADMIN or SUPER_ADMIN."""
    return require_roles(RoleEnum.ADMIN, RoleEnum.SUPER_ADMIN)


def require_super_admin():
    """Dependency: SUPER_ADMIN only."""
    return require_roles(RoleEnum.SUPER_ADMIN)


def assert_any_role(user: User, *required: RoleEnum, detail: str = "Forbidden") -> None:
    """Imperative variant for inline use inside a handler."""
    if not has_any_role(user, *required):
        raise HTTPException(status_code=403, detail=detail)


def assert_admin(user: User, detail: str = "Admins only") -> None:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail=detail)
