import os
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# The ledger's union and account_service.get_account_balances state the SAME row set twice — which
# rows reach an account, with which sign, bounded below by opening_date. Nothing in the type system
# ties them together, and the unit suite mocks every repository, so a branch that drifts (a missing
# source, a flipped sign, a bound that stops matching) yields a self-consistent but wrong balance
# column that no other test can see. These assert the two agree against a real Postgres, one case per
# movement type plus the shapes that have caused defects before: a pre-opening row, an unlinked row,
# another tenant's row, and both legs of a cross-currency transfer.
#
# Skipped unless LEDGER_TEST_DATABASE_URL points at a database with the schema applied, so the default
# `pnpm test:api` run stays unit-only — the same contract test_rls_isolation.py uses.
from app.repositories import account_movement_repository, account_repository
from app.services import account_service

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_OPENING = date(2026, 7, 1)
_OPENING_BALANCE = Decimal("100000.00")


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(DB_URL)
    async with AsyncSession(engine) as s:
        yield s
        await s.rollback()
    await engine.dispose()


# Two users, two accounts for the first (so a transfer has somewhere to go) and one for the second
# (so cross-tenant leakage would show). Rolled back by the fixture, so nothing persists.
@pytest_asyncio.fixture
async def fixtures(session: AsyncSession):
    async def scalar(sql: str, **params):
        return (await session.execute(text(sql), params)).scalar_one()

    users = [
        await scalar(
            "INSERT INTO users (name, email, password_hash) VALUES (:n, :e, 'x') RETURNING id",
            n="Ledger A",
            e="ledger_drift_a@test.local",
        ),
        await scalar(
            "INSERT INTO users (name, email, password_hash) VALUES (:n, :e, 'x') RETURNING id",
            n="Ledger B",
            e="ledger_drift_b@test.local",
        ),
    ]

    async def account(user_id: int, name: str, currency: str, opening: Decimal):
        return await scalar(
            "INSERT INTO accounts (user_id, name, type, currency, opening_balance, opening_date) VALUES (:u, :n, 'bank', :c, :b, :d) RETURNING id",
            u=user_id,
            n=name,
            c=currency,
            b=opening,
            d=_OPENING,
        )

    ars = await account(users[0], "Ledger ARS", "ARS", _OPENING_BALANCE)
    usd = await account(users[0], "Ledger USD", "USD", Decimal("0.00"))
    other = await account(users[1], "Other tenant", "ARS", Decimal("5000.00"))

    card = await scalar(
        "INSERT INTO credit_cards (user_id, name, currency, closing_day, due_day) VALUES (:u, 'Ledger card', 'ARS', 20, 10) RETURNING id",
        u=users[0],
    )
    return {"users": users, "ars": ars, "usd": usd, "other": other, "card": card}


# Asserts the ledger's own sum and the accounts page's balance agree for the given account.
async def _assert_no_drift(session: AsyncSession, account_id: int, user_id: int):
    account = await account_repository.get_by_id(session, account_id, user_id)
    from_balance_path = await account_service.get_account_balance(session, account, user_id)
    from_union = await account_movement_repository.sum_movements(session, account_id, user_id, opening_date=account.opening_date)
    assert account.opening_balance + from_union == from_balance_path, (
        f"the ledger union and get_account_balances disagree on account {account_id}: "
        f"opening {account.opening_balance} + union {from_union} != balance {from_balance_path}"
    )
    return from_balance_path


class TestUnionMatchesTheBalance:
    @pytest.mark.asyncio
    async def test_an_untouched_account_is_its_opening_balance(self, session, fixtures):
        assert await _assert_no_drift(session, fixtures["ars"], fixtures["users"][0]) == _OPENING_BALANCE

    @pytest.mark.asyncio
    async def test_every_movement_type_together(self, session, fixtures):
        u, ars, usd, card = fixtures["users"][0], fixtures["ars"], fixtures["usd"], fixtures["card"]
        await session.execute(
            text(
                "INSERT INTO income_entries (user_id, date, amount, currency, category, account_id)"
                " VALUES (:u, '2026-07-05', 200000, 'ARS', 'salary', :a)"
            ),
            {"u": u, "a": ars},
        )
        await session.execute(
            text(
                "INSERT INTO expense_entries (user_id, date, amount, currency, category, account_id)"
                " VALUES (:u, '2026-07-10', 12000, 'ARS', 'food', :a)"
            ),
            {"u": u, "a": ars},
        )
        await session.execute(
            text(
                "INSERT INTO card_settlements (credit_card_id, user_id, date, amount, currency, account_id)"
                " VALUES (:c, :u, '2026-07-15', 8000, 'ARS', :a)"
            ),
            {"c": card, "u": u, "a": ars},
        )
        # Cross-currency, so each leg must sum in its OWN account's currency with no conversion.
        await session.execute(
            text(
                "INSERT INTO transfers (user_id, from_account_id, to_account_id, date, from_amount, to_amount)"
                " VALUES (:u, :f, :t, '2026-07-25', 50000, 40)"
            ),
            {"u": u, "f": ars, "t": usd},
        )
        await session.flush()

        assert await _assert_no_drift(session, ars, u) == Decimal("230000.00")
        # The other side of the same transfer, proving the leg is credited in the destination's currency.
        assert await _assert_no_drift(session, usd, u) == Decimal("40.00")

    @pytest.mark.asyncio
    async def test_a_reconciliation_adjustment_counts_once(self, session, fixtures):
        u, ars = fixtures["users"][0], fixtures["ars"]
        rec = (
            await session.execute(
                text(
                    "INSERT INTO account_reconciliations (user_id, account_id, as_of_date, statement_balance,"
                    " computed_balance, difference) VALUES (:u, :a, '2026-08-12', 98500, 100000, -1500) RETURNING id"
                ),
                {"u": u, "a": ars},
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO expense_entries (user_id, date, amount, currency, category, account_id, source,"
                " account_reconciliation_id) VALUES (:u, '2026-08-12', 1500, 'ARS', 'account_adjustment', :a,"
                " 'reconciliation', :r)"
            ),
            {"u": u, "a": ars, "r": rec},
        )
        await session.flush()
        # The adjustment is an ordinary expense row, so it must be counted by the entry branch and
        # NOT a second time as a reconciliation.
        assert await _assert_no_drift(session, ars, u) == Decimal("98500.00")

    @pytest.mark.asyncio
    async def test_rows_the_balance_excludes_are_excluded_here_too(self, session, fixtures):
        u, ars = fixtures["users"][0], fixtures["ars"]
        await session.execute(
            text(
                "INSERT INTO expense_entries (user_id, date, amount, currency, category, account_id) VALUES"
                # Pre-opening: opening_balance already contains it, so counting it double-counts.
                " (:u, '2026-06-15', 30000, 'ARS', 'food', :a),"
                # Unlinked: attributed to no account at all.
                " (:u, '2026-07-20', 9999, 'ARS', 'food', NULL)"
            ),
            {"u": u, "a": ars},
        )
        await session.flush()
        assert await _assert_no_drift(session, ars, u) == _OPENING_BALANCE

    @pytest.mark.asyncio
    async def test_another_tenants_rows_never_reach_this_ledger(self, session, fixtures):
        await session.execute(
            text(
                "INSERT INTO expense_entries (user_id, date, amount, currency, category, account_id)"
                " VALUES (:u, '2026-07-11', 777, 'ARS', 'food', :a)"
            ),
            {"u": fixtures["users"][1], "a": fixtures["other"]},
        )
        await session.flush()
        assert await _assert_no_drift(session, fixtures["ars"], fixtures["users"][0]) == _OPENING_BALANCE


class TestLedgerWalksBackToOpening:
    @pytest.mark.asyncio
    async def test_the_oldest_rows_balance_lands_on_the_opening_balance(self, session, fixtures):
        u, ars = fixtures["users"][0], fixtures["ars"]
        # Enough rows to span pages, all on colliding dates so the tie-break is exercised too.
        await session.execute(
            text(
                "INSERT INTO expense_entries (user_id, date, amount, currency, category, account_id)"
                " SELECT :u, DATE '2026-07-02' + (g % 3), 100 + g, 'ARS', 'dining', :a"
                " FROM generate_series(1, 30) g"
            ),
            {"u": u, "a": ars},
        )
        await session.flush()

        from app.models.user import User

        user = User(id=u, email="ledger_drift_a@test.local", password_hash="x", session_epoch=0)
        from app.services import account_movement_service

        seen: list = []
        page = 1
        while True:
            response = await account_movement_service.list_account_movements(session, ars, user, page=page, page_size=7)
            if not response.items or page > response.total:
                break
            seen.extend(response.items)
            if len(seen) >= response.total:
                break
            page += 1

        keys = [(m.source, m.source_id) for m in seen]
        assert len(set(keys)) == len(keys) == 30, "pagination duplicated or dropped a row"
        oldest = seen[-1]
        assert oldest.balance_after - oldest.amount == _OPENING_BALANCE
        newest = seen[0]
        assert newest.balance_after == await _assert_no_drift(session, ars, u)
