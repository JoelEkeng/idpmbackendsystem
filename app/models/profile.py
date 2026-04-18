from datetime import date
from sqlalchemy import String, Enum, ForeignKey, Boolean, Index, Date, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.models.base import UUIDMixin, TimestampMixin
from app.core.database import Base
from app.models.enums import RoleEnum, MaritalStatus
from sqlalchemy import DateTime
from typing import List



class Profile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "profiles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    fullname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)

    role: Mapped[RoleEnum] = mapped_column(
        Enum(RoleEnum, name="role_enum"),
        default=RoleEnum.MEMBER,
        index=True,
        nullable=False,
    )

    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    marital_status: Mapped[MaritalStatus | None] = mapped_column(
        Enum(MaritalStatus, name="marital_status_enum"),
        nullable=True,
    )

    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String(20), nullable=True)
    emergency_name: Mapped[str | None] = mapped_column(String(20), nullable=True)
    department: Mapped[str | None] = mapped_column(String(50), nullable=True)

    profile_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="profile",
    )

    attendances: Mapped[List["Attendance"]] = relationship(
    back_populates="profile"
    )

    __table_args__ = (
        Index("ix_profile_role_completed", "role", "profile_completed"),
    )