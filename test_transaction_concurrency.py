import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.api.v1.router import attendance, dashboard, finance, group
from app.models.enums import GroupMembershipStatus
from app.models.finance import PaymentType


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class DashboardResult:
    def one(self):
        return 4, 4, 3, 12, Decimal("125.50")


@pytest.mark.asyncio
async def test_admin_summary_uses_one_database_execution(monkeypatch):
    class Session:
        calls = 0

        async def execute(self, statement):
            self.calls += 1
            return DashboardResult()

    async def cache_miss(key):
        return None

    async def cache_set(key, value, ttl):
        return None

    monkeypatch.setattr(dashboard, "cache_get_json", cache_miss)
    monkeypatch.setattr(dashboard, "cache_set_json", cache_set)
    monkeypatch.setattr(dashboard, "is_admin", lambda user: True)
    session = Session()

    result = await dashboard.admin_dashboard_summary(session, object())

    assert session.calls == 1
    assert result == {
        "total_members": 4,
        "total_groups": 4,
        "total_services": 3,
        "total_attendance": 12,
        "total_revenue": 125.5,
    }


@pytest.mark.asyncio
async def test_concurrent_duplicate_attendance_has_one_winner():
    class Shared:
        lock = asyncio.Lock()
        inserted = False

    class Session:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0
            self.sql = ""

        async def execute(self, statement):
            self.sql = str(statement.compile(dialect=postgresql.dialect()))
            async with Shared.lock:
                if Shared.inserted:
                    return ScalarResult(None)
                Shared.inserted = True
                return ScalarResult(uuid4())

        async def commit(self):
            self.commits += 1

        async def rollback(self):
            self.rollbacks += 1

    first = Session()
    second = Session()
    profile_id = uuid4()
    service_id = uuid4()

    outcomes = await asyncio.gather(
        attendance._record_attendance(first, profile_id, service_id, attendance.datetime.now()),
        attendance._record_attendance(second, profile_id, service_id, attendance.datetime.now()),
    )

    assert sorted(outcomes) == [False, True]
    assert first.commits + second.commits == 1
    assert first.rollbacks + second.rollbacks == 1
    assert "ON CONFLICT ON CONSTRAINT uq_attendance_profile_service DO NOTHING" in first.sql


class MembershipState:
    def __init__(self, status):
        self.status = status
        self.lock = asyncio.Lock()


class MembershipSession:
    def __init__(self, shared):
        self.shared = shared

    async def execute(self, statement):
        compiled = statement.compile(dialect=postgresql.dialect())
        expected = set(compiled.params["status_1"])
        new_status = compiled.params["status"]
        async with self.shared.lock:
            if self.shared.status not in expected:
                return ScalarResult(None)
            self.shared.status = new_status
            return ScalarResult(SimpleNamespace(status=new_status))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("initial", "expected", "target"),
    [
        (GroupMembershipStatus.PENDING, (GroupMembershipStatus.PENDING,), GroupMembershipStatus.LEADER_APPROVED),
        (
            GroupMembershipStatus.LEADER_APPROVED,
            (GroupMembershipStatus.LEADER_APPROVED,),
            GroupMembershipStatus.APPROVED,
        ),
    ],
)
async def test_concurrent_group_approval_has_one_winner(initial, expected, target):
    shared = MembershipState(initial)
    membership_id = uuid4()

    outcomes = await asyncio.gather(
        group._transition_membership(MembershipSession(shared), membership_id, expected, target, "actor-1"),
        group._transition_membership(MembershipSession(shared), membership_id, expected, target, "actor-2"),
    )

    assert sum(outcome is not None for outcome in outcomes) == 1
    assert shared.status == target


@pytest.mark.asyncio
async def test_concurrent_group_approval_vs_rejection_has_valid_final_state():
    shared = MembershipState(GroupMembershipStatus.PENDING)
    membership_id = uuid4()

    approved, rejected = await asyncio.gather(
        group._transition_membership(
            MembershipSession(shared),
            membership_id,
            (GroupMembershipStatus.PENDING,),
            GroupMembershipStatus.LEADER_APPROVED,
            "leader",
        ),
        group._transition_membership(
            MembershipSession(shared),
            membership_id,
            (GroupMembershipStatus.PENDING, GroupMembershipStatus.LEADER_APPROVED),
            GroupMembershipStatus.REJECTED,
            "admin",
        ),
    )

    assert approved is not None or rejected is not None
    assert shared.status in {GroupMembershipStatus.LEADER_APPROVED, GroupMembershipStatus.REJECTED}


class FinanceState:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.total = Decimal("0")
        self.stats = Decimal("0")


class FinanceSession:
    def __init__(self, shared, amount, profile_id):
        self.shared = shared
        self.amount = Decimal(amount)
        self.profile_id = profile_id
        self.local_stats = Decimal("0")
        self.locked = False
        self.commits = 0

    async def flush(self):
        return None

    async def scalar(self, statement):
        sql = str(statement.compile(dialect=postgresql.dialect()))
        assert "FOR UPDATE" in sql
        await self.shared.lock.acquire()
        self.locked = True
        return self.profile_id

    async def execute(self, statement):
        sql = str(statement.compile(dialect=postgresql.dialect()))
        if sql.startswith("SELECT"):
            total = self.shared.total + self.amount
            return SimpleNamespace(all=lambda: [(PaymentType.tithe, total)])
        assert "ON CONFLICT" in sql
        self.local_stats = self.shared.total + self.amount
        return SimpleNamespace()

    async def commit(self):
        self.shared.total += self.amount
        self.shared.stats = self.local_stats
        self.commits += 1
        if self.locked:
            self.shared.lock.release()
            self.locked = False


@pytest.mark.asyncio
async def test_concurrent_finance_stats_are_serialized_per_profile():
    shared = FinanceState()
    profile_id = uuid4()
    first = FinanceSession(shared, "10.00", profile_id)
    second = FinanceSession(shared, "20.00", profile_id)

    async def update(session):
        await finance.update_finance_stats(profile_id, session)
        await session.commit()

    await asyncio.gather(update(first), update(second))

    assert shared.total == Decimal("30.00")
    assert shared.stats == Decimal("30.00")
    assert first.commits == second.commits == 1
