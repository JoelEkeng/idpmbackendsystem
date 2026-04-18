from pydantic import BaseModel
from decimal import Decimal
from uuid import UUID
from datetime import datetime
from enum import Enum


class PaymentType(str, Enum):
    tithe = "tithe"
    dues = "dues"
    donation = "donation"


class PaymentInitiate(BaseModel):
    payment_type: PaymentType
    amount: Decimal | None = None


class ManualPaymentCreate(BaseModel):
    profile_id: UUID
    payment_type: PaymentType
    amount: Decimal


class FinanceRead(BaseModel):
    id: UUID
    profile_id: UUID
    profile_name: str
    payment_type: PaymentType
    amount: Decimal
    status: str
    payment_method: str
    reference: str
    paid_at: datetime | None

    class Config:
        from_attributes = True


class FinanceSummary(BaseModel):
    total_tithes: Decimal
    total_dues: Decimal
    total_donations: Decimal
    pending_transactions: int