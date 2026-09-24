import os
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Re-reconciling a date REPLACES the row it already carries, and the three things that makes true live
# entirely in the database — a mocked session can watch the ORDER of the steps and nothing else.
#
#   * THE UNIQUE CONSTRAINT. Two rows on one date were the whole defect: the delete guard compares
#     DATES, so both held the maximum and both were deletable, and dropping the older one took its
#     adjustment while the survivor's recorded computed_balance still counted it. Measured on a clean
#     account at HEAD: reconcile 2026-07-20 to 72,500, then again to 75,000 — the account read 75,000
#     across two rows, and deleting the first was ACCEPTED and left it reading 2,500 with a row on
#     screen still claiming 75,000. The constraint makes that state unrepresentable, which is why it is
#     asserted here as a refused INSERT rather than as behaviour some code path chooses.
#
#   * THE CASCADE. The replace only lands the right figure if the superseded row's adjustment is really
#     gone from the ledger before the fresh balance is summed — a DELETE plus an ON DELETE CASCADE plus
#     a flush, none of which a mock performs.
#
#   * THE PREVIEW AGREEING WITH THE WRITE. The reconcile dialog previews the balance by SUBTRACTING the
#     superseded row's difference, while the write deletes the row and re-derives from the ledger. Two
#     derivations of one fact, and the unit suite cannot see them disagree because it stubs every sum —
#     so each case below reads the preview, then saves, and asserts the row the save recorded carries
#     exactly the figure the user was shown.
#
# Skipped unless LEDGER_TEST_DATABASE_URL points at a database with the schema applied, so the default
# `pnpm test:api` run stays unit-only — the same contract test_account_ledger_drift.py uses. It is the
# OWNER-role variable because these WRITE, and because the services commit: the fixture cleans up by
# deleting its user rather than by rolling back.
from app.models.user import User
from app.services import account_reconciliation_service as recon
from app.services import account_service

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_EMAIL = "recon_replace@test.local"
_DATE = date(2026, 7, 20)
_OPENING = Decimal("50000.00")
_OPENING_DATE = date(2026, 1, 1)


# One user and one account with a known opening balance and no movements, so every figure below is the
# opening balance plus exactly the adjustments under test. Services commit, so teardown deletes the
# user and lets ON DELETE CASCADE take the account, its reconciliations and their adjustments.
@pytest_asyncio.fixture
async def seeded():
    engine = create_async_engine(DB_URL)
    async with AsyncSession(engine) as session:
        await _cleanup(session)
        row = (
            await session.execute(
                text("INSERT INTO users (name, email, password_hash) VALUES ('Replace', :e, 'x') RETURNING id, session_epoch"),
                {"e": _EMAIL},
            )
        ).one()
        user = User(id=row.id, email=_EMAIL, password_hash="x", session_epoch=row.session_epoch)
        account_id = (
            await session.execute(
                text(
                    "INSERT INTO accounts (user_id, name, type, currency, opening_balance, opening_date) "
                    "VALUES (:u, 'Caja', 'bank', 'ARS', :b, :d) RETURNING id"
                ),
                {"u": user.id, "b": _OPENING, "d": _OPENING_DATE},
            )
        ).scalar_one()
        await session.commit()

        yield {"session": session, "user": user, "account_id": account_id}

        await _cleanup(session)
        await session.commit()
    await engine.dispose()


async def _cleanup(session: AsyncSession) -> None:
    await session.execute(text("DELETE FROM users WHERE email = :e"), {"e": _EMAIL})


# The account's live balance, through the same derivation the accounts page renders.
async def _balance(seeded) -> Decimal:
    account = await account_service.get_account_in_scope(seeded["session"], seeded["account_id"], seeded["user"])
    return (await account_service.get_account_balances(seeded["session"], [account], seeded["user"].id))[seeded["account_id"]]


async def _reconcile(seeded, statement: Decimal, *, as_of: date = _DATE):
    return await recon.create_or_replace(seeded["session"], seeded["account_id"], seeded["user"], as_of_date=as_of, statement_balance=statement)


async def _row_count(seeded) -> int:
    return (
        await seeded["session"].execute(text("SELECT count(*) FROM account_reconciliations WHERE account_id = :a"), {"a": seeded["account_id"]})
    ).scalar_one()


# Every adjustment row the account carries, across both private tables, as (table, amount) pairs.
async def _adjustments(seeded) -> list[tuple[str, Decimal]]:
    rows = (
        await seeded["session"].execute(
            text(
                "SELECT 'income' AS kind, amount FROM income_entries WHERE account_id = :a AND account_reconciliation_id IS NOT NULL"
                " UNION ALL"
                " SELECT 'expense', amount FROM expense_entries WHERE account_id = :a AND account_reconciliation_id IS NOT NULL"
                " ORDER BY 1, 2"
            ),
            {"a": seeded["account_id"]},
        )
    ).all()
    return [(kind, amount) for kind, amount in rows]


class TestTheSameDateHoldsOneRow:
    @pytest.mark.asyncio
    async def test_a_second_reconciliation_on_the_date_replaces_the_first(self, seeded):
        first = await _reconcile(seeded, Decimal("72500.00"))
        assert await _balance(seeded) == Decimal("72500.00")

        second = await _reconcile(seeded, Decimal("75000.00"))

        assert await _row_count(seeded) == 1
        assert second.id != first.id
        assert await _balance(seeded) == Decimal("75000.00")
        # The survivor measures against the UNTOUCHED ledger, not against what the superseded row left
        # behind. Appending recorded 72,500 here and a difference of 2,500 — the gap between two
        # statements rather than the gap this reconciliation actually closed.
        assert second.computed_balance == _OPENING
        assert second.difference == Decimal("25000.00")
        # And exactly one adjustment survives, sized to that difference. The first one's 22,500 is gone.
        assert await _adjustments(seeded) == [("income", Decimal("25000.00"))]

    @pytest.mark.asyncio
    async def test_deleting_the_survivor_returns_the_account_to_where_it_started(self, seeded):
        # The defect, stated as its consequence. With two rows the older one was deletable and took its
        # adjustment with it while the newer one kept claiming a balance built on top of it. With one
        # row there is one thing to delete and it undoes the whole true-up.
        await _reconcile(seeded, Decimal("72500.00"))
        survivor = await _reconcile(seeded, Decimal("75000.00"))

        await recon.delete_reconciliation(seeded["session"], seeded["account_id"], survivor.id, seeded["user"])

        assert await _row_count(seeded) == 0
        assert await _adjustments(seeded) == []
        assert await _balance(seeded) == _OPENING

    @pytest.mark.asyncio
    async def test_the_database_refuses_a_second_row_on_the_date_outright(self, seeded):
        # Asserted against a direct INSERT rather than through the service, because the point is that
        # the two-row state cannot be reached AT ALL — not that one code path declines to reach it. A
        # scheduler, an import, a migration or a future caller gets the same refusal.
        existing = await _reconcile(seeded, Decimal("72500.00"))

        with pytest.raises(IntegrityError) as exc:
            await seeded["session"].execute(
                text(
                    "INSERT INTO account_reconciliations (user_id, account_id, as_of_date, statement_balance, computed_balance, difference)"
                    " VALUES (:u, :a, :d, 1, 1, 0)"
                ),
                {"u": seeded["user"].id, "a": seeded["account_id"], "d": existing.as_of_date},
            )
        assert "account_reconciliations_account_date_key" in str(exc.value)
        await seeded["session"].rollback()

    @pytest.mark.asyncio
    async def test_a_different_date_still_appends(self, seeded):
        # The constraint is per DATE, not per account. Reconciling forward has to keep working, and a
        # constraint on account_id alone would pass every test above while breaking it.
        await _reconcile(seeded, Decimal("72500.00"))
        await _reconcile(seeded, Decimal("75000.00"), as_of=date(2026, 7, 21))

        assert await _row_count(seeded) == 2
        assert await _balance(seeded) == Decimal("75000.00")


class TestThePreviewMatchesWhatGetsWritten:
    # The dialog SUBTRACTS the superseded row's difference; the write DELETES the row and re-derives.
    # Each case reconciles once to put an adjustment on the date, reads the preview, then reconciles
    # again and asserts the recorded computed_balance is the figure the preview showed.

    @pytest.mark.parametrize(
        ("first_statement", "label"),
        [
            (Decimal("72500.00"), "a surplus already posted on that date"),
            (Decimal("30000.00"), "a shortfall already posted on that date"),
            (_OPENING, "a matched reconciliation, which wrote no adjustment"),
        ],
    )
    @pytest.mark.asyncio
    async def test_the_preview_is_the_balance_the_save_measures_against(self, seeded, first_statement, label):
        await _reconcile(seeded, first_statement)

        preview = await recon.get_computed_balance(seeded["session"], seeded["account_id"], seeded["user"], as_of_date=_DATE)
        written = await _reconcile(seeded, Decimal("81234.56"))

        assert preview.replaces_existing is True, label
        assert preview.balance == written.computed_balance == _OPENING, label
        # And the difference the user was promised is the one that got posted.
        assert Decimal("81234.56") - preview.balance == written.difference, label

    @pytest.mark.asyncio
    async def test_a_free_date_previews_the_plain_balance_and_says_so(self, seeded):
        preview = await recon.get_computed_balance(seeded["session"], seeded["account_id"], seeded["user"], as_of_date=_DATE)

        assert preview.replaces_existing is False
        assert preview.balance == _OPENING
