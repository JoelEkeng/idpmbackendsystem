from datetime import datetime
from sqlalchemy import ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid import UUID

from app.models.base import Base, UUIDMixin, TimestampMixin


class Attendance(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "attendances"

    service_id: Mapped[UUID] = mapped_column(
        ForeignKey("services.id"),
        nullable=False
    )

    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.id"),
        nullable=False
    )

    check_in_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    service = relationship("Service", back_populates="attendances")
    profile = relationship("Profile", back_populates="attendances")

    __table_args__ = (
        UniqueConstraint("profile_id", "service_id", name="uq_attendance_profile_service"),
    )