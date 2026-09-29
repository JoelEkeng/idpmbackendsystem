from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.router import equipment, finance
from app.models.enums import RoleEnum
from app.schemas.equipment import EquipmentCreate
from app.schemas.finance import ManualPaymentCreate, PaymentType
from app.utils.auth import get_current_user


class AuthResult:
    def __init__(self, row):
        self.row = row

    def unique(self):
        return self

    def one_or_none(self):
        return self.row


class AuthSession:
    def __init__(self, row):
        self.row = row

    async def execute(self, statement):
        return AuthResult(self.row)


@pytest.mark.asyncio
async def test_valid_database_session_returns_user():
    user = SimpleNamespace(id="user-1", profile=SimpleNamespace(roles=[RoleEnum.USER]))
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)

    assert await get_current_user("Bearer opaque-session", AuthSession((user, expires))) is user


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("authorization", "detail"),
    [
        (None, "Missing Authorization header"),
        ("Basic value", "Invalid auth header"),
        ("Bearer invalid", "Invalid session"),
    ],
)
async def test_unauthorized_and_invalid_sessions_return_401(authorization, detail):
    with pytest.raises(HTTPException) as error:
        await get_current_user(authorization, AuthSession(None))

    assert error.value.status_code == 401
    assert error.value.detail == detail


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expires",
    [
        datetime.now(timezone.utc) - timedelta(seconds=1),
        datetime.utcnow() - timedelta(seconds=1),
    ],
)
async def test_expired_database_session_returns_401(expires):
    user = SimpleNamespace(id="user-1", profile=SimpleNamespace(roles=[RoleEnum.USER]))

    with pytest.raises(HTTPException) as error:
        await get_current_user("Bearer expired", AuthSession((user, expires)))

    assert error.value.status_code == 401
    assert error.value.detail == "Session expired"


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FinanceSession:
    def __init__(self, target_profile, membership=None, group=None):
        self.target_profile = target_profile
        self.membership = membership
        self.group = group
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    async def get(self, model, key):
        if model.__name__ == "Profile":
            return self.target_profile
        if model.__name__ == "Group":
            return self.group
        return None

    async def execute(self, statement):
        return ScalarResult(self.membership)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_manual_payment_rejects_unauthorized_member():
    profile_id = uuid4()
    db = FinanceSession(SimpleNamespace(id=profile_id, user_id="target-user"))
    user = SimpleNamespace(
        id="ordinary-user",
        profile=SimpleNamespace(id=uuid4(), roles=[RoleEnum.USER]),
    )
    payload = ManualPaymentCreate(
        profile_id=profile_id,
        payment_type=PaymentType.tithe,
        amount=Decimal("10.00"),
    )

    with pytest.raises(HTTPException) as error:
        await finance.manual_payment(payload, db, user)

    assert error.value.status_code == 403
    assert not db.added
    assert db.commits == 0


@pytest.mark.asyncio
async def test_manual_payment_commits_for_finance_role(monkeypatch):
    profile_id = uuid4()
    db = FinanceSession(SimpleNamespace(id=profile_id, user_id="target-user"))
    user = SimpleNamespace(
        id="finance-user",
        profile=SimpleNamespace(id=uuid4(), roles=[RoleEnum.USER, RoleEnum.FINANCE]),
    )
    payload = ManualPaymentCreate(
        profile_id=profile_id,
        payment_type=PaymentType.dues,
        amount=Decimal("20.00"),
    )
    stats_calls = []
    invalidated = []

    async def update_stats(target, session):
        stats_calls.append(target)

    async def cache_delete(*keys):
        invalidated.extend(keys)

    monkeypatch.setattr(finance, "update_finance_stats", update_stats)
    monkeypatch.setattr(finance, "cache_delete", cache_delete)

    assert await finance.manual_payment(payload, db, user) == {"message": "Payment recorded"}
    assert len(db.added) == 1
    assert db.commits == 1
    assert stats_calls == [profile_id]
    assert set(invalidated) == {
        finance._ADMIN_FINANCE_SUMMARY_CACHE_KEY,
        finance._ADMIN_DASHBOARD_CACHE_KEY,
    }


@pytest.mark.asyncio
async def test_equipment_cache_hit_avoids_database(monkeypatch):
    expected = [{"id": "EQ-1", "name": "Mic"}]

    async def cache_hit(key):
        return expected

    class Session:
        async def execute(self, statement):
            raise AssertionError("database should not be queried on a cache hit")

    monkeypatch.setattr(equipment, "is_admin", lambda user: True)
    monkeypatch.setattr(equipment, "cache_get_json", cache_hit)

    assert await equipment.get_equipments(25, 50, Session(), object()) == expected


@pytest.mark.asyncio
async def test_equipment_mutation_invalidates_all_pages(monkeypatch):
    invalidated = []

    class Session:
        async def get(self, model, key):
            return None

        def add(self, value):
            self.value = value

        async def commit(self):
            return None

        async def refresh(self, value):
            return None

    async def delete_prefix(prefix):
        invalidated.append(prefix)

    monkeypatch.setattr(equipment, "is_admin", lambda user: True)
    monkeypatch.setattr(equipment, "cache_delete_prefix", delete_prefix)
    payload = EquipmentCreate(
        id="EQ-1",
        name="Microphone",
        quantity=2,
        state="good",
    )

    await equipment.create_equipment(payload, Session(), object())

    assert invalidated == [equipment._EQUIPMENT_CACHE_PREFIX]


def test_removed_frontend_endpoint_references_do_not_return():
    api_source = (
        Path(__file__).resolve().parents[1] / "frontend" / "lib" / "api.ts"
    ).read_text()

    assert 'request<Member>(`/users/${id}`)' not in api_source
    assert 'request<Transaction[]>("/finance/transactions"' not in api_source
    assert 'request<Transaction>("/finance/transactions"' not in api_source
