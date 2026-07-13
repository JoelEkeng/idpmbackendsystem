from datetime import datetime
from sqlalchemy import ForeignKey, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid import UUID

from app.models.base import Base, UUIDMixin, TimestampMixin


class Attendance(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "attendances"

    service_id: Mapped[UUID] = mapped_column(
        ForeignKey("services.id"),
        nullable=False,
        index=True,
    )

    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.id"),
        nullable=False,
        index=True,
    )

    check_in_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    service = relationship("Service", back_populates="attendances")
    profile = relationship("Profile", back_populates="attendances")

    __table_args__ = (
        UniqueConstraint("profile_id", "service_id", name="uq_attendance_profile_service"),
        # Filter-by-service + newest-first ordering (attendance monitor page).
        Index(
            "ix_attendance_service_checkin",
            "service_id",
            "check_in_time",
            postgresql_ops={"check_in_time": "DESC"},
        ),
        # Filter-by-profile + newest-first ordering (member history page).
        Index(
            "ix_attendance_profile_checkin",
            "profile_id",
            "check_in_time",
            postgresql_ops={"check_in_time": "DESC"},
        ),
    )