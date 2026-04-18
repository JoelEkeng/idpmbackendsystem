from datetime import datetime
from decimal import Decimal
from uuid import UUID
import enum

from sqlalchemy import (
    String,
    DateTime,
    ForeignKey,
    Numeric,
    Enum,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, UUIDMixin, TimestampMixin


class PaymentType(str, enum.Enum):
    tithe = "tithe"
    dues = "dues"
    donation = "donation"


class PaymentMethod(str, enum.Enum):
    online = "online"
    manual = "manual"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    success = "success"
    failed = "failed"


class FinanceTransaction(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "finance_transactions"

    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.id"), nullable=False
    )

    payment_type: Mapped[PaymentType] = mapped_column(
        Enum(PaymentType), nullable=False
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )

    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod), nullable=False
    )

    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus), default=PaymentStatus.pending
    )

    reference: Mapped[str] = mapped_column(
        String, unique=True, index=True
    )

    paystack_reference: Mapped[str | None] = mapped_column(String)

    recorded_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("profiles.id")
    )

    paid_at: Mapped[datetime | None] = mapped_column(DateTime)

    profile = relationship(
        "Profile",
        foreign_keys=[profile_id]
    )

    __table_args__ = (
        UniqueConstraint("reference"),
    )


class DueConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "due_configs"

    name: Mapped[str] = mapped_column(String)
    amount: Mapped[Decimal] = mapped_column(Numeric(12,2))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProfileFinanceStats(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "profile_finance_stats"

    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.id"), unique=True
    )

    total_tithes: Mapped[Decimal] = mapped_column(
        Numeric(12,2), default=0
    )

    total_dues: Mapped[Decimal] = mapped_column(
        Numeric(12,2), default=0
    )

    total_donations: Mapped[Decimal] = mapped_column(
        Numeric(12,2), default=0
    )

    pending_transactions: Mapped[int] = mapped_column(default=0)