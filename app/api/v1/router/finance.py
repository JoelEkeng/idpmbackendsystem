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

from app.core.config import get_settings
from app.core.cache import cache_get_json, cache_set_json, cache_delete
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
from app.models.group import Group, GroupMember
from app.models.enums import RoleEnum, GroupMembershipStatus

from dotenv import load_dotenv

load_dotenv()


router = APIRouter(prefix="/finance", tags=["Finance"])

_ADMIN_FINANCE_SUMMARY_CACHE_KEY = "finance:admin-summary"
_ADMIN_FINANCE_SUMMARY_TTL = 60

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

        amount = due.amount if due else 50

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
                "callback_url": f"{get_settings().FRONTEND_URL}/payment-success",
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
    await cache_delete(_ADMIN_FINANCE_SUMMARY_CACHE_KEY)

    return {"status": "success"}

async def update_finance_stats(profile_id, db):
    # SQL-side aggregation instead of loading every transaction row into
    # Python just to sum() three subsets of it.
    result = await db.execute(
        select(
            FinanceTransaction.payment_type,
            func.coalesce(func.sum(FinanceTransaction.amount), 0),
        )
        .where(
            FinanceTransaction.profile_id == profile_id,
            FinanceTransaction.status == PaymentStatus.success,
        )
        .group_by(FinanceTransaction.payment_type)
    )
    totals = dict(result.all())

    tithes = totals.get(PaymentType.tithe, 0)
    dues = totals.get(PaymentType.dues, 0)
    donations = totals.get(PaymentType.donation, 0)

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
    # Recording a manual payment marks money as received, so it's restricted
    # to the finance team / admins, OR a group leader recording a payment for
    # one of their own (APPROVED) group members — never for anyone else's.
    privileged = has_any_role(user, RoleEnum.FINANCE, RoleEnum.ADMIN, RoleEnum.SUPER_ADMIN)
    if not privileged:
        target_profile = await db.get(Profile, payload.profile_id)
        if not target_profile:
            raise HTTPException(404, "Profile not found")

        membership_q = await db.execute(
            select(GroupMember).where(
                GroupMember.user_id == target_profile.user_id,
                GroupMember.status == GroupMembershipStatus.APPROVED,
            )
        )
        membership = membership_q.scalar_one_or_none()
        group = await db.get(Group, membership.group_id) if membership else None
        is_own_group_member = bool(group and group.leader_id == user.id)
        if not is_own_group_member:
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
    await cache_delete(_ADMIN_FINANCE_SUMMARY_CACHE_KEY)

    return {"message": "Payment recorded"}


@router.get("/ledger", response_model=list[FinanceRead])
async def get_ledger(
    status: PaymentStatus | None = Query(None),
    payment_type: PaymentType | None = Query(None),
    user_id: str | None = Query(None),
    group_id: str | None = Query(None),
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

    if group_id:
        # Only that group's leader (or a privileged user) may filter by it.
        group = await db.get(Group, group_id)
        if not group:
            raise HTTPException(404, "Group not found")
        if not privileged and group.leader_id != current_user.id:
            raise HTTPException(403, "Only that group's leader can view this")
    elif not privileged:
        # Force scoping to the caller.
        user_id = current_user.id

    # Start from FinanceTransaction and join Profile → User
    query = (
        select(FinanceTransaction, Profile.fullname)
        .join(FinanceTransaction.profile)  # Join Profile via profile_id
        .join(Profile.user)                # Join User via profile.user_id
    )

    if group_id:
        query = query.join(
            GroupMember,
            (GroupMember.user_id == User.id)
            & (GroupMember.group_id == group_id)
            & (GroupMember.status == GroupMembershipStatus.APPROVED),
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

    cached = await cache_get_json(_ADMIN_FINANCE_SUMMARY_CACHE_KEY)
    if cached is not None:
        return cached

    # Aggregate totals from ProfileFinanceStats
    result = await db.execute(
        select(
            func.coalesce(func.sum(ProfileFinanceStats.total_tithes), 0),
            func.coalesce(func.sum(ProfileFinanceStats.total_dues), 0),
            func.coalesce(func.sum(ProfileFinanceStats.total_donations), 0),
        )
    )
    total_tithes, total_dues, total_donations = result.fetchone()

    # Aggregate counts and total amounts from FinanceTransaction by status
    # in a single query instead of three sequential round trips.
    status_result = await db.execute(
        select(
            FinanceTransaction.status,
            func.count(FinanceTransaction.id),
            func.coalesce(func.sum(FinanceTransaction.amount), 0),
        )
        .where(FinanceTransaction.status.in_(
            [PaymentStatus.pending, PaymentStatus.success, PaymentStatus.failed]
        ))
        .group_by(FinanceTransaction.status)
    )

    status_metrics = {
        row[0]: {"count": row[1], "total": row[2]} for row in status_result.all()
    }

    pending_metrics = status_metrics.get(PaymentStatus.pending, {"count": 0, "total": 0})
    success_metrics = status_metrics.get(PaymentStatus.success, {"count": 0, "total": 0})
    failed_metrics = status_metrics.get(PaymentStatus.failed, {"count": 0, "total": 0})

    pending_count, pending_total = (
        pending_metrics["count"],
        pending_metrics["total"],
    )
    success_count, total_paid = (
        success_metrics["count"],
        success_metrics["total"],
    )
    failed_count, failed_total = (
        failed_metrics["count"],
        failed_metrics["total"],
    )

    payload = {
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
    await cache_set_json(_ADMIN_FINANCE_SUMMARY_CACHE_KEY, payload, ttl=_ADMIN_FINANCE_SUMMARY_TTL)
    return payload


@router.post("/verify")
async def verify_payment(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reference = payload.get("reference")
    if not reference:
        raise HTTPException(400, "Reference is required")

    # Check DB first
    result = await db.execute(
        select(FinanceTransaction).where(FinanceTransaction.reference == reference)
    )
    transaction = result.scalar_one_or_none()

    # Only the transaction's owner or an admin/finance user may verify/view it.
    if transaction:
        owner = current_user.profile and transaction.profile_id == current_user.profile.id
        if not owner and not has_any_role(
            current_user, RoleEnum.FINANCE, RoleEnum.ADMIN, RoleEnum.SUPER_ADMIN
        ):
            raise HTTPException(403, "Not allowed to verify this transaction")

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