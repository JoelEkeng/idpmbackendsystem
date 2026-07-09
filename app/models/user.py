from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "user"  # IMPORTANT: singular

    # Primary key (BetterAuth usually uses string IDs)
    id: Mapped[str] = mapped_column(String, primary_key=True)

    # Basic fields
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    emailVerified: Mapped[bool] = mapped_column(Boolean, default=False)
    image: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Timestamps
    createdAt: Mapped[datetime] = mapped_column(DateTime)
    updatedAt: Mapped[datetime] = mapped_column(DateTime)

    # Your internal app relationship
    profile = relationship(
        "Profile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # One-to-many memberships (but constrained to one active)
    memberships: Mapped[list["GroupMember"]] = relationship(
        "GroupMember",
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="GroupMember.user_id",
    )

    # If user is a group leader
    led_groups: Mapped[list["Group"]] = relationship(
        "Group",
        back_populates="leader",
        foreign_keys="Group.leader_id",
    )