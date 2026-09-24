import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Every repository `get_by_id` that takes a `user_id` refuses a row belonging to somebody else — proven
# by running the real query against a real Postgres with two users' rows in the table.
#
# ▸ WHY THIS CANNOT BE A UNIT TEST. The predicate IS the behaviour. A mocked session returns whatever
# the test told it to, so a unit test asserting "another user's row comes back as None" passes exactly
# as well after the predicate is deleted — which is not a hypothetical: deleting
# `X.user_id == user_id` from the investment, account, credit_card and collection repositories left the
# entire 2877-test unit suite green. Four of these twelve were named in the pre-launch audit; the other
# eight have the identical shape and were unpinned for the same reason.
#
# ▸ WHY BOTH HALVES OF EACH CASE. Each case asserts the owner DOES get the row and the other user does
# NOT. Without the first half a predicate mutated to something permanently false — `1 == 0`, a typo
# comparing the column to itself — passes the cross-tenant half perfectly while breaking the feature.
#
# ▸ WHY RLS IS NOT THE ANSWER HERE. The row-level policies do backstop the ordinary case, where the
# `user_id` passed is the caller's own. They cannot backstop the case these predicates exist for:
# `shared_expense_service._load_card_id` asks "does this card belong to THE NAMED PAYER", who is not
# the caller, and `app_current_user_id()` has no opinion about that. See TestCrossMemberFunding below.
#
# The population is DERIVED, not listed: `tests/unit/test_ownership_predicate_coverage.py` walks
# `app/repositories` for every `get_by_id` taking a `user_id` and fails when one has no case here — so
# the next repository added does not quietly join the unpinned set.
#
# Skipped unless LEDGER_TEST_DATABASE_URL points at a database with the schema applied, so the default
# `pnpm test:api` run stays unit-only. It is the OWNER-role variable because these seed rows for two
# different users, which no single app-role session may do.
from app.domain import NotFoundError
from app.models.group import GroupMember
from app.models.group_money_settings import SplitMethod
from app.models.user import User
from app.repositories import (
    account_repository,
    api_key_repository,
    collection_repository,
    credit_card_repository,
    expense_repository,
    income_repository,
    installment_repository,
    investment_repository,
    notification_repository,
    payment_obligation_repository,
    subscription_repository,
    transfer_repository,
)
from app.schemas.shared_expense import SharedExpenseSplitInput
from app.services import group_settlement_service, shared_expense_service

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_EMAILS = ("own_a@test.local", "own_b@test.local")
_DATE = date(2026, 7, 1)


# One case per repository: how to create a row owned by a given user, and how to read it back scoped to
# a given user. `read` is spelled out per case rather than derived from the module, because
# `notification_repository.get_by_id` takes its arguments in the other order — a generic driver would
# have silently passed the id as the user and the user as the id, and every assertion would still have
# come out the colour the test wanted.
@dataclass(frozen=True)
class _Case:
    repository: str
    seed: Callable[[AsyncSession, int], Awaitable[int]]
    read: Callable[[AsyncSession, int, int], Awaitable[object | None]]


async def _insert(session: AsyncSession, sql: str, **params) -> int:
    return (await session.execute(text(sql), params)).scalar_one()


async def _seed_account(s: AsyncSession, user_id: int, name: str = "own-account") -> int:
    return await _insert(
        s,
        "INSERT INTO accounts (user_id, name, type, currency, opening_balance, opening_date) VALUES (:u, :n, 'bank', 'ARS', 0, :d) RETURNING id",
        u=user_id,
        n=name,
        d=_DATE,
    )


async def _seed_transfer(s: AsyncSession, user_id: int) -> int:
    origin = await _seed_account(s, user_id, "own-transfer-from")
    target = await _seed_account(s, user_id, "own-transfer-to")
    return await _insert(
        s,
        "INSERT INTO transfers (user_id, from_account_id, to_account_id, date, from_amount, to_amount) VALUES (:u, :f, :t, :d, 1, 1) RETURNING id",
        u=user_id,
        f=origin,
        t=target,
        d=_DATE,
    )


_CASES = (
    _Case(
        "account_repository",
        _seed_account,
        lambda s, row, user: account_repository.get_by_id(s, row, user),
    ),
    _Case(
        "api_key_repository",
        lambda s, u: _insert(
            s,
            "INSERT INTO api_keys (user_id, name, key_hash, key_prefix) VALUES (:u, 'own', :h, :p) RETURNING id",
            u=u,
            h=f"hash-{u}",
            p=f"pre{u}",
        ),
        lambda s, row, user: api_key_repository.get_by_id(s, row, user),
    ),
    _Case(
        "collection_repository",
        lambda s, u: _insert(s, "INSERT INTO investment_collections (user_id, name) VALUES (:u, 'own') RETURNING id", u=u),
        lambda s, row, user: collection_repository.get_by_id(s, row, user),
    ),
    _Case(
        "credit_card_repository",
        lambda s, u: _insert(
            s,
            "INSERT INTO credit_cards (user_id, name, closing_day, due_day, currency) VALUES (:u, 'own', 10, 20, 'ARS') RETURNING id",
            u=u,
        ),
        lambda s, row, user: credit_card_repository.get_by_id(s, row, user),
    ),
    _Case(
        "expense_repository",
        lambda s, u: _insert(
            s,
            "INSERT INTO expense_entries (user_id, date, amount, currency) VALUES (:u, :d, 1, 'ARS') RETURNING id",
            u=u,
            d=_DATE,
        ),
        lambda s, row, user: expense_repository.get_by_id(s, row, user),
    ),
    _Case(
        "income_repository",
        lambda s, u: _insert(
            s,
            "INSERT INTO income_entries (user_id, date, amount, currency) VALUES (:u, :d, 1, 'ARS') RETURNING id",
            u=u,
            d=_DATE,
        ),
        lambda s, row, user: income_repository.get_by_id(s, row, user),
    ),
    _Case(
        "installment_repository",
        lambda s, u: _insert(
            s,
            "INSERT INTO installments (user_id, name, total_amount, installment_amount, currency, installments_count, start_date)"
            " VALUES (:u, 'own', 12, 1, 'ARS', 12, :d) RETURNING id",
            u=u,
            d=_DATE,
        ),
        lambda s, row, user: installment_repository.get_by_id(s, row, user),
    ),
    _Case(
        "investment_repository",
        lambda s, u: _insert(
            s,
            "INSERT INTO investments (user_id, name, category, base_currency) VALUES (:u, 'own', 'cedears', 'ARS') RETURNING id",
            u=u,
        ),
        lambda s, row, user: investment_repository.get_by_id(s, row, user),
    ),
    _Case(
        "notification_repository",
        lambda s, u: _insert(s, "INSERT INTO notifications (user_id, event) VALUES (:u, 'snapshot_due') RETURNING id", u=u),
        # Arguments in the other order — the reason `read` is written out per case.
        lambda s, row, user: notification_repository.get_by_id(s, user, row),
    ),
    _Case(
        "payment_obligation_repository",
        lambda s, u: _insert(
            s,
            "INSERT INTO payment_obligations (user_id, name, amount, currency, next_due_date, anchor_day)"
            " VALUES (:u, 'own', 1, 'ARS', :d, 1) RETURNING id",
            u=u,
            d=_DATE,
        ),
        lambda s, row, user: payment_obligation_repository.get_by_id(s, row, user),
    ),
    _Case(
        "subscription_repository",
        lambda s, u: _insert(
            s,
            "INSERT INTO subscriptions (user_id, name, amount, currency, billing_cycle, next_billing_date, anchor_day)"
            " VALUES (:u, 'own', 1, 'ARS', 'monthly', :d, 1) RETURNING id",
            u=u,
            d=_DATE,
        ),
        lambda s, row, user: subscription_repository.get_by_id(s, row, user),
    ),
    _Case(
        "transfer_repository",
        _seed_transfer,
        lambda s, row, user: transfer_repository.get_by_id(s, row, user),
    ),
)

# Imported by the coverage guard in tests/unit/, which compares it against the repositories on disk.
COVERED_REPOSITORIES = frozenset(case.repository for case in _CASES)


# Two users with nothing in common. Every row these tests create hangs off one of them, so teardown
# deletes the pair and lets ON DELETE CASCADE take the rest.
@pytest_asyncio.fixture
async def users():
    engine = create_async_engine(DB_URL)
    async with AsyncSession(engine) as session:
        await _cleanup(session)
        ids = [
            await _insert(
                session,
                "INSERT INTO users (name, email, password_hash) VALUES (:n, :e, 'x') RETURNING id",
                n=email.split("@")[0],
                e=email,
            )
            for email in _EMAILS
        ]
        await session.commit()

        yield {"session": session, "a": ids[0], "b": ids[1]}

        await session.rollback()
        await _cleanup(session)
        await session.commit()
    await engine.dispose()


# Clears the group-scoped rows BEFORE the users, and that order is load-bearing rather than tidy.
# `shared_expenses.credit_card_id` is ON DELETE RESTRICT, so a shared expense left behind blocks the
# cascade from `users` → `credit_cards` and the teardown fails — which poisons every later run rather
# than the one that created it. A row gets left behind exactly when the cross-member guard below stops
# working, so the failure mode this avoids is the one where a real regression makes the whole file
# error out at setup and stops reporting which predicate broke. (Found by mutating the card predicate:
# eight unrelated cases went from "caught" to "error" and the sweep was measuring a poisoned database.)
async def _cleanup(session: AsyncSession) -> None:
    groups = "SELECT id FROM groups WHERE name = 'own_group'"
    await session.execute(text(f"DELETE FROM shared_expense_splits WHERE group_id IN ({groups})"))
    await session.execute(text(f"DELETE FROM shared_expenses WHERE group_id IN ({groups})"))
    await session.execute(text(f"DELETE FROM group_settlements WHERE group_id IN ({groups})"))
    await session.execute(text(f"DELETE FROM group_members WHERE group_id IN ({groups})"))
    await session.execute(text("DELETE FROM groups WHERE name = 'own_group'"))
    await session.execute(text("DELETE FROM users WHERE email = ANY(:e)"), {"e": list(_EMAILS)})


class TestEveryOwnerScopedRead:
    @pytest.mark.parametrize("case", _CASES, ids=[case.repository for case in _CASES])
    @pytest.mark.asyncio
    async def test_it_returns_the_row_to_its_owner_and_nothing_to_anyone_else(self, users, case):
        session = users["session"]
        row_id = await case.seed(session, users["a"])
        await session.flush()

        assert await case.read(session, row_id, users["a"]) is not None, f"{case.repository} hid a row from its own owner"
        assert await case.read(session, row_id, users["b"]) is None, f"{case.repository} handed a row to another user"


# The two funding rules that ask "does this instrument belong to THAT MEMBER" rather than "to the
# caller". RLS answers the second question and has no way to answer the first, so whatever refuses
# these is doing it alone — which is worth knowing precisely, because the two sites turn out to differ.
class TestCrossMemberFunding:
    @pytest.mark.asyncio
    async def test_a_payer_cannot_be_charged_on_somebody_elses_card(self, users):
        # The real exploit, driven end to end: Alice creates a shared expense, names BOB as the person
        # who fronted it, and passes HER OWN card. RLS is satisfied — it is her card and she is the
        # caller — so the only thing between this and a recorded debt that says Bob paid with a card he
        # does not own is `credit_card_repository.get_by_id`'s `user_id` predicate.
        session = users["session"]
        group_id, seats = await _seed_group(session, users)
        card_id = await _insert(
            session,
            "INSERT INTO credit_cards (user_id, name, closing_day, due_day, currency) VALUES (:u, 'alice-card', 10, 20, 'ARS') RETURNING id",
            u=users["a"],
        )
        await session.commit()

        with pytest.raises(NotFoundError):
            await shared_expense_service.create_expense(
                session,
                group_id,
                _user(users["a"]),
                date=_DATE,
                amount=Decimal("100.00"),
                currency="ARS",
                split_method=SplitMethod.equal,
                splits=[SharedExpenseSplitInput(member_id=seats["a"]), SharedExpenseSplitInput(member_id=seats["b"])],
                payer_member_id=seats["b"],
                credit_card_id=card_id,
            )
        await session.rollback()

    @pytest.mark.asyncio
    async def test_a_settlement_leg_for_another_member_is_refused_before_ownership_is_even_asked(self, users):
        # ▸ THE AUDIT OVERSTATED THIS SITE. It listed `_load_own_account` beside the card rule as a
        # second place RLS cannot backstop. It is not equivalent: all three of its call sites run
        # `_ensure_own_leg` first, which refuses naming an account for anyone but yourself — so by the
        # time `_load_own_account` runs, the member IS the caller and RLS applies after all.
        #
        # Asserted as the ERROR THAT COMES BACK, because that is the only way to tell which layer
        # refused. `GroupSettlementForeignLegError` means the front guard did; `NotFoundError` would
        # mean it had been removed and the ownership predicate caught it as a bare "not found".
        session = users["session"]
        group_id, seats = await _seed_group(session, users)
        account_id = await _seed_account(session, users["a"], "alice-settle")
        await session.commit()

        with pytest.raises(group_settlement_service.GroupSettlementForeignLegError):
            await group_settlement_service.record_settlement(
                session,
                group_id,
                _user(users["a"]),
                from_member_id=seats["b"],
                to_member_id=seats["a"],
                date=_DATE,
                amount=Decimal("10.00"),
                currency="ARS",
                from_account_id=account_id,
            )
        await session.rollback()

    @pytest.mark.asyncio
    async def test_and_the_ownership_backstop_underneath_it_refuses_too(self, users):
        # The other half of the same claim: `_ensure_own_leg` being the first refusal does not make the
        # ownership check decorative. Called directly with a member who is not the account's owner — the
        # state the front guard prevents — it still refuses, so relaxing that guard could not silently
        # open the path. Both layers, each proven on the row that would need it.
        session = users["session"]
        account_id = await _seed_account(session, users["a"], "alice-backstop")
        await session.flush()
        bob = GroupMember(id=1, group_id=1, user_id=users["b"], display_name="bob", role="member")

        with pytest.raises(NotFoundError):
            await group_settlement_service._load_own_account(session, bob, account_id)
        await session.rollback()


def _user(user_id: int) -> User:
    return User(id=user_id, email=f"u{user_id}@test.local", password_hash="x", session_epoch=0)


# A group both users sit in, returning its id and the two seat ids. The minimum a shared expense needs
# before it can get as far as resolving who funded it.
async def _seed_group(session: AsyncSession, users: dict) -> tuple[int, dict[str, int]]:
    group_id = await _insert(
        session,
        "INSERT INTO groups (name, kind, created_by) VALUES ('own_group', 'household', :u) RETURNING id",
        u=users["a"],
    )
    seats = {
        key: await _insert(
            session,
            "INSERT INTO group_members (group_id, user_id, display_name, role, joined_at) VALUES (:g, :u, :n, 'member', NOW()) RETURNING id",
            g=group_id,
            u=users[key],
            n=key,
        )
        for key in ("a", "b")
    }
    return group_id, seats
