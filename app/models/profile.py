from datetime import date
from sqlalchemy import String, Enum, ForeignKey, Boolean, Index, Date, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY
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

    roles: Mapped[List[RoleEnum]] = mapped_column(
        ARRAY(Enum(RoleEnum, name="role_enum", create_constraint=False)),
        default=lambda: [RoleEnum.USER],
        server_default="{USER}",
        nullable=False,
    )

    def has_role(self, role: RoleEnum) -> bool:
        """True if this profile has the given role assigned."""
        if not self.roles:
            return False
        # Roles can come back as enum values or raw strings depending on driver.
        return any(
            (r == role) or (getattr(r, "value", r) == role.value)
            for r in self.roles
        )

    @property
    def is_admin(self) -> bool:
        """ADMIN or SUPER_ADMIN (full app access)."""
        return self.has_role(RoleEnum.ADMIN) or self.has_role(RoleEnum.SUPER_ADMIN)

    @property
    def is_super_admin(self) -> bool:
        return self.has_role(RoleEnum.SUPER_ADMIN)

    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    marital_status: Mapped[MaritalStatus | None] = mapped_column(
        Enum(MaritalStatus, name="marital_status_enum"),
        nullable=True,
    )

    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String(20), nullable=True)
    emergency_name: Mapped[str | None] = mapped_column(String(20), nullable=True)
    department: Mapped[str | None] = mapped_column(String(50), nullable=True)

    fingerprint_id: Mapped[str | None] = mapped_column(
        String(50),
        unique=True,
        nullable=True,  # allow null for users without fingerprint
        index=True,
    )

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
        Index("ix_profile_roles", "roles", postgresql_using="gin"),
        Index("ix_profile_completed", "profile_completed"),
    )