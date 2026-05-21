from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy import Date, Time, Integer, String
from app.models.base import Base, UUIDMixin, TimestampMixin
from typing import List
from datetime import date, time


class Service(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "services"

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    date: Mapped[date] = mapped_column(Date, nullable=False)

    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)

    grace_before_minutes: Mapped[int] = mapped_column(Integer, default=30)
    grace_after_minutes: Mapped[int] = mapped_column(Integer, default=15)

    attendances: Mapped[List["Attendance"]] = relationship(
        back_populates="service",
        cascade="all, delete-orphan"
    )