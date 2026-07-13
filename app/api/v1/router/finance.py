import uuid
import httpx
import os
import hmac
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.finance import (
    FinanceTransaction,
    PaymentType,
    PaymentMethod,
    PaymentStatus,
    DueConfig,
    ProfileFinanceStats,
)
from app.schemas.finance import (
    PaymentInitiate,
    ManualPaymentCreate,
    FinanceRead,
    FinanceSummary,
)

from app.utils.auth import get_current_user
from app.utils.permissions import is_admin, has_any_role
from app.models.user import User
from app.models.profile import Profile
from app.models.enums import RoleEnum

from dotenv import load_dotenv

load_dotenv()


router = APIRouter(prefix="/finance", tags=["Finance"])

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_INIT_URL = "https://api.paystack.co/transaction/initialize"

@router.post("/initiate")
async def initiate_payment(
    payload: PaymentInitiate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    amount = payload.amount

    if payload.payment_type == PaymentType.dues:

        result = await db.execute(
            select(DueConfig).where(DueConfig.active == True)
        )

        due = result.scalar_one_or_none()

        if not due:
            raise HTTPException(400, "No active dues configured")

        amount = due.amount

    if payload.payment_type in [PaymentType.tithe, PaymentType.donation] and not amount:
        raise HTTPException(400, "Amount required")

    reference = str(uuid.uuid4())

    transaction = FinanceTransaction(
        profile_id=user.profile.id,
        payment_type=payload.payment_type,
        amount=amount,
        payment_method=PaymentMethod.online,
        status=PaymentStatus.pending,
        reference=reference,
    )

    db.add(transaction)
    await db.commit()

    async with httpx.AsyncClient() as client:

        response = await client.post(
            PAYSTACK_INIT_URL,
            headers={
                "Authorization": f"Bearer {PAYSTACK_SECRET}",
                "Content-Type": "application/json",
            },
            json={
                "email": user.email,
                "amount": int(amount * 100),
                "reference": reference,
                "callback_url": "http://localhost:3000/payment-success",
            },
        )

    paystack_data = response.json()

    if not paystack_data.get("status") or "data" not in paystack_data:
        raise HTTPException(
            status_code=400,
            detail=f"Paystack error: {paystack_data.get('message', 'No message')}"
        )

    return {
        "authorization_url": paystack_data["data"]["authorization_url"],
        "reference": reference,
    }


@router.post("/webhook")
async def paystack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):

    if not PAYSTACK_SECRET:
        raise HTTPException(503, "Payment provider not configured")

    body = await request.body()

    signature = request.headers.get("x-paystack-signature")

    hash = hmac.new(
        PAYSTACK_SECRET.encode(),
        body,
        hashlib.sha512
    ).hexdigest()

    if not signature or not hmac.compare_digest(hash, signature):
        raise HTTPException(400, "Invalid webhook")

    payload = await request.json()

    reference = payload["data"]["reference"]

    result = await db.execute(
        select(FinanceTransaction).where(
            FinanceTransaction.reference == reference
        )
    )

    transaction = result.scalar_one_or_none()

    if not transaction:
        return {"status": "ignored"}

    if transaction.status == PaymentStatus.success:
        return {"status": "already_processed"}

    transaction.status = PaymentStatus.success
    transaction.paid_at = datetime.utcnow()

    await db.commit()

    await update_finance_stats(transaction.profile_id, db)

    return {"status": "success"}

async def update_finance_stats(profile_id, db):

    result = await db.execute(
        select(FinanceTransaction).where(
            FinanceTransaction.profile_id == profile_id,
            FinanceTransaction.status == PaymentStatus.success,
        )
    )

    transactions = result.scalars().all()

    tithes = sum(
        t.amount for t in transactions if t.payment_type == PaymentType.tithe
    )

    dues = sum(
        t.amount for t in transactions if t.payment_type == PaymentType.dues
    )

    donations = sum(
        t.amount for t in transactions if t.payment_type == PaymentType.donation
    )

    result = await db.execute(
        select(ProfileFinanceStats).where(
            ProfileFinanceStats.profile_id == profile_id
        )
    )

    stats = result.scalar_one_or_none()

    if not stats:

        stats = ProfileFinanceStats(
            profile_id=profile_id,
            total_tithes=tithes,
            total_dues=dues,
            total_donations=donations,
        )

        db.add(stats)

    else:

        stats.total_tithes = tithes
        stats.total_dues = dues
        stats.total_donations = donations

    await db.commit()


@router.post("/manual")
async def manual_payment(
    payload: ManualPaymentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Recording a manual payment marks money as received, so it must be
    # restricted to the finance team / admins.
    if not has_any_role(user, RoleEnum.FINANCE, RoleEnum.ADMIN, RoleEnum.SUPER_ADMIN):
        raise HTTPException(403, "Finance access required")

    reference = str(uuid.uuid4())
    transaction = FinanceTransaction(
        profile_id=payload.profile_id,
        payment_type=payload.payment_type,
        amount=payload.amount,
        payment_method=PaymentMethod.manual,
        status=PaymentStatus.success,
        recorded_by=user.profile.id,
        reference=reference,
        paid_at=datetime.utcnow(),
    )

    db.add(transaction)
    await db.commit()

    await update_finance_stats(payload.profile_id, db)

    return {"message": "Payment recorded"}


@router.get("/ledger", response_model=list[FinanceRead])
async def get_ledger(
    status: PaymentStatus | None = Query(None),
    payment_type: PaymentType | None = Query(None),
    user_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Finance team, admins, and super admins can read the full ledger.
    # Regular users can only read their own rows.
    privileged = has_any_role(
        current_user, RoleEnum.FINANCE, RoleEnum.ADMIN, RoleEnum.SUPER_ADMIN
    )
    if not privileged:
        # Force scoping to the caller.
        user_id = current_user.id
    # Start from FinanceTransaction and join Profile → User
    query = (
        select(FinanceTransaction, Profile.fullname)
        .join(FinanceTransaction.profile)  # Join Profile via profile_id
        .join(Profile.user)                # Join User via profile.user_id
    )

    if user_id:
        query = query.where(User.id == user_id)
    if status:
        query = query.where(FinanceTransaction.status == status)
    if payment_type:
        query = query.where(FinanceTransaction.payment_type == payment_type)

    query = query.order_by(FinanceTransaction.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    rows = result.all()

    # Map only the fields FinanceRead needs, avoiding SQLAlchemy internal state
    # (e.g. _sa_instance_state) leaking from the ORM object's __dict__.
    ledger = [
        {
            "id": txn.id,
            "profile_id": txn.profile_id,
            "profile_name": fullname,
            "payment_type": txn.payment_type,
            "amount": txn.amount,
            "status": txn.status,
            "payment_method": txn.payment_method,
            "reference": txn.reference,
            "paid_at": txn.paid_at,
        }
        for txn, fullname in rows
    ]

    return ledger

@router.get("/summary", response_model=FinanceSummary)
async def finance_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    result = await db.execute(
        select(ProfileFinanceStats).where(
            ProfileFinanceStats.profile_id == user.profile.id
        )
    )

    stats = result.scalar_one_or_none()

    if not stats:
        return FinanceSummary(
            total_tithes=0,
            total_dues=0,
            total_donations=0,
            pending_transactions=0,
        )

    return stats



@router.get("/admin/summary")
async def admin_finance_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not has_any_role(current_user, RoleEnum.FINANCE, RoleEnum.ADMIN, RoleEnum.SUPER_ADMIN):
        raise HTTPException(403, "Finance access required")

    # Aggregate totals from ProfileFinanceStats
    result = await db.execute(
        select(
            func.coalesce(func.sum(ProfileFinanceStats.total_tithes), 0),
            func.coalesce(func.sum(ProfileFinanceStats.total_dues), 0),
            func.coalesce(func.sum(ProfileFinanceStats.total_donations), 0),
        )
    )
    total_tithes, total_dues, total_donations = result.fetchone()

    # Aggregate counts and total amounts from FinanceTransaction
    result = await db.execute(
        select(
            func.count(FinanceTransaction.id),
            func.coalesce(func.sum(FinanceTransaction.amount), 0)
        )
        .where(FinanceTransaction.status == PaymentStatus.pending)
    )
    pending_count, pending_total = result.fetchone()

    result = await db.execute(
        select(
            func.count(FinanceTransaction.id),
            func.coalesce(func.sum(FinanceTransaction.amount), 0)
        )
        .where(FinanceTransaction.status == PaymentStatus.success)
    )
    success_count, total_paid = result.fetchone()

    result = await db.execute(
        select(
            func.count(FinanceTransaction.id),
            func.coalesce(func.sum(FinanceTransaction.amount), 0)
        )
        .where(FinanceTransaction.status == PaymentStatus.failed)
    )
    failed_count, failed_total = result.fetchone()

    return {
        "total_tithes": total_tithes,
        "total_dues": total_dues,
        "total_donations": total_donations,
        "total_revenue": total_paid,  # total amount successfully paid
        "pending_transactions": pending_count,
        "pending_total": pending_total,
        "successful_transactions": success_count,
        "failed_transactions": failed_count,
        "failed_total": failed_total,
    }


@router.post("/verify")
async def verify_payment(
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    reference = payload.get("reference")
    if not reference:
        raise HTTPException(400, "Reference is required")

    # Check DB first
    result = await db.execute(
        select(FinanceTransaction).where(FinanceTransaction.reference == reference)
    )
    transaction = result.scalar_one_or_none()

    if transaction and transaction.status == PaymentStatus.success:
        return {"status": "success"}

    # Verify with Paystack API
    VERIFY_URL = f"https://api.paystack.co/transaction/verify/{reference}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            VERIFY_URL,
            headers={"Authorization": f"Bearer {PAYSTACK_SECRET}"}
        )
        data = resp.json()

    if not data.get("status") or data["data"]["status"] != "success":
        return {"status": "failed"}

    # Update transaction in DB
    if transaction:
        transaction.status = PaymentStatus.success
        transaction.paid_at = datetime.utcnow()
        await db.commit()
        await update_finance_stats(transaction.profile_id, db)

    return {"status": "success"}