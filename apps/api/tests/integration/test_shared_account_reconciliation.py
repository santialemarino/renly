import os
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# A POT's account becoming reconcilable, proven against a real Postgres — the three properties of it
# that live entirely in the database and that no mocked session can see.
#
#   * WHICH ROW A RECONCILIATION LOCKS, and why it differs by scope. A locking read is governed by the
#     UPDATE policy rather than the SELECT one, so "can this caller take the lock" is a policy question
#     with a different answer per table. Reconciling requires only that the pot be VISIBLE, and
#     accounts_scope_write requires pot WRITE access — so locking the account would silently take no
#     lock for a read-only co-owner, which is the whole reason the pot's own row is locked instead.
#
#   * THE BALANCE, AS A SUM OVER SOURCES. compute_account_balance_at and get_account_balances are two
#     derivations of one fact, and a source present in one and absent from the other makes the
#     reconciliation post an adjustment for money the account really did move. The unit suite pins the
#     ELEVEN-source enumeration with mocked sums; this drives both over a POT's account holding a real
#     row from every source that can reach one, which is the half a mock cannot answer.
#
#   * THE TWO CHECK CONSTRAINTS AND THE CASCADE that make the adjustment pair honest: a reconciliation
#     may only carry its own scope's kind of adjustment, and deleting one takes the row it created —
#     and that row's splits — with it.
#
# Uses the same env vars as test_rls_isolation.py so the RLS suites run together, and skips silently
# when they are unset.
from app.db import set_session_user
from app.domain import AccountReconciliationPotNotDividedError, reconciliation_refusal
from app.repositories import account_reconciliation_repository, pot_ownership_repository
from app.services import account_reconciliation_service, account_service

APP_URL = os.getenv("RLS_TEST_DATABASE_URL")
ADMIN_URL = os.getenv("RLS_TEST_ADMIN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not APP_URL or not ADMIN_URL,
    reason="set RLS_TEST_DATABASE_URL + RLS_TEST_ADMIN_DATABASE_URL (a real Postgres with the RLS schema) to run these",
)

_EMAILS = {
    # Holds 60% of the pot and may WRITE it.
    "writer": "recon_writer@test.local",
    # Holds 40% and may only VIEW it — the seat the whole locking decision is about.
    "viewer": "recon_viewer@test.local",
}

_GROUP = "recon_shared_group"
_OPENING = Decimal("1000.00")

# Every money source that can reach a POT's account, with the sign it carries — the enumeration this
# file exists to walk. Each gets a DISTINCT figure below, so a term the formula drops, or reads with the
# wrong sign, changes the answer; equal figures would let a dropped `+x` and a dropped `-x` cancel.
#
# The four private sources (income_entries, expense_entries, card_settlements and a private transfer)
# are deliberately absent and CANNOT appear: those tables keep user_id NOT NULL and carry no pot_id, so
# they never name a pot-owned account. `test_a_private_row_naming_this_account_splits_the_two_answers`
# below constructs the row that would break that and names the layer which refuses it.
_SOURCES = (
    ("ownership_in", Decimal("70.00"), 1),
    ("ownership_out", Decimal("14.00"), -1),
    ("shared_expense", Decimal("21.00"), -1),
    ("shared_income", Decimal("28.00"), 1),
    ("group_settlement_in", Decimal("35.00"), 1),
    ("group_settlement_out", Decimal("42.00"), -1),
    ("transfer_in", Decimal("49.00"), 1),
    ("transfer_out", Decimal("56.00"), -1),
)

_EXPECTED_BALANCE = _OPENING + sum(sign * amount for _name, amount, sign in _SOURCES)


# Seeds a group of two, a pot divided 60/40, TWO accounts that pot holds, and one row of every source
# that can reach the first of them. The second account exists so a pot-to-pot transfer has somewhere to
# go — a transfer may not cross a scope boundary, so a shared account's transfer legs only exist in
# pairs.
@pytest_asyncio.fixture
async def seeded():
    admin_engine = create_async_engine(ADMIN_URL)
    app_engine = create_async_engine(APP_URL)
    app_sessionmaker = sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    admin_sessionmaker = sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False)

    async with admin_sessionmaker() as s:
        await _cleanup(s)
        users = {}
        for key, email in _EMAILS.items():
            users[key] = (
                await s.execute(
                    text("INSERT INTO users (name, email, password_hash) VALUES (:n, :e, 'h') RETURNING id"),
                    {"n": key, "e": email},
                )
            ).scalar_one()

        group = (
            await s.execute(
                text("INSERT INTO groups (name, kind, created_by) VALUES (:g, 'household', :u) RETURNING id"),
                {"g": _GROUP, "u": users["writer"]},
            )
        ).scalar_one()
        seats = {}
        for key in ("writer", "viewer"):
            seats[key] = (
                await s.execute(
                    text(
                        "INSERT INTO group_members (group_id, user_id, display_name, role, joined_at) "
                        "VALUES (:g, :u, :n, 'member', NOW()) RETURNING id"
                    ),
                    {"g": group, "u": users[key], "n": key},
                )
            ).scalar_one()

        pot = (
            await s.execute(
                text("INSERT INTO pots (group_id, base_currency, is_default) VALUES (:g, 'ARS', TRUE) RETURNING id"),
                {"g": group},
            )
        ).scalar_one()
        # The writer may write; the viewer may only view. That asymmetry is the subject of the locking
        # tests, so it is explicit on both rows rather than left to the pot's visibility default.
        for key, can_write in (("writer", True), ("viewer", False)):
            await s.execute(
                text("INSERT INTO pot_member_permissions (pot_id, member_id, can_view, can_write) VALUES (:p, :m, TRUE, :w)"),
                {"p": pot, "m": seats[key], "w": can_write},
            )
        # 60/40, deliberately uneven: an equal split is indistinguishable from an ownership one.
        for key, units in (("writer", 60), ("viewer", 40)):
            await s.execute(
                text(
                    "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, units, unit_price) "
                    "VALUES (:p, 'opening', '2026-01-01', :m, :u, 1)"
                ),
                {"p": pot, "m": seats[key], "u": units},
            )

        accounts = []
        for name in ("shared_main", "shared_other"):
            accounts.append(
                (
                    await s.execute(
                        text(
                            "INSERT INTO accounts (pot_id, created_by, name, type, currency, opening_balance, opening_date) "
                            "VALUES (:p, :u, :n, 'bank', 'ARS', :b, '2026-01-01') RETURNING id"
                        ),
                        {"p": pot, "u": users["writer"], "n": name, "b": _OPENING if name == "shared_main" else 0},
                    )
                ).scalar_one()
            )
        main, other = accounts
        figures = {name: amount for name, amount, _sign in _SOURCES}

        # A contribution credits the pot's account (its `to` leg is base_amount); a withdrawal debits it
        # (its `from` leg is base_amount). Both name a pot account on one side only, which is what makes
        # each leg a separate term.
        await s.execute(
            text(
                "INSERT INTO pot_ownership_events "
                "(pot_id, type, date, member_id, units, unit_price, amount, amount_currency, base_amount, to_account_id) "
                "VALUES (:p, 'contribution', '2026-02-01', :m, 1, 1, :a, 'ARS', :a, :acc)"
            ),
            {"p": pot, "m": seats["writer"], "a": figures["ownership_in"], "acc": main},
        )
        await s.execute(
            text(
                "INSERT INTO pot_ownership_events "
                "(pot_id, type, date, member_id, units, unit_price, amount, amount_currency, base_amount, from_account_id) "
                "VALUES (:p, 'withdrawal', '2026-02-02', :m, 1, 1, :a, 'ARS', :a, :acc)"
            ),
            {"p": pot, "m": seats["writer"], "a": figures["ownership_out"], "acc": main},
        )
        await s.execute(
            text(
                "INSERT INTO shared_expenses (group_id, date, amount, currency, split_method, paid_from_account_id) "
                "VALUES (:g, '2026-02-03', :a, 'ARS', 'equal', :acc)"
            ),
            {"g": group, "a": figures["shared_expense"], "acc": main},
        )
        await s.execute(
            text(
                "INSERT INTO shared_income (group_id, date, amount, currency, split_method, destination, paid_to_account_id) "
                "VALUES (:g, '2026-02-04', :a, 'ARS', 'equal', 'joint', :acc)"
            ),
            {"g": group, "a": figures["shared_income"], "acc": main},
        )
        await s.execute(
            text(
                "INSERT INTO group_settlements (group_id, from_member_id, to_member_id, date, amount, currency, to_account_id, to_amount) "
                "VALUES (:g, :f, :t, '2026-02-05', :a, 'ARS', :acc, :a)"
            ),
            {"g": group, "f": seats["viewer"], "t": seats["writer"], "a": figures["group_settlement_in"], "acc": main},
        )
        await s.execute(
            text(
                "INSERT INTO group_settlements (group_id, from_member_id, to_member_id, date, amount, currency, from_account_id, from_amount) "
                "VALUES (:g, :f, :t, '2026-02-06', :a, 'ARS', :acc, :a)"
            ),
            {"g": group, "f": seats["writer"], "t": seats["viewer"], "a": figures["group_settlement_out"], "acc": main},
        )
        await s.execute(
            text(
                "INSERT INTO transfers (pot_id, from_account_id, to_account_id, date, from_amount, to_amount) "
                "VALUES (:p, :f, :t, '2026-02-07', :a, :a)"
            ),
            {"p": pot, "f": other, "t": main, "a": figures["transfer_in"]},
        )
        await s.execute(
            text(
                "INSERT INTO transfers (pot_id, from_account_id, to_account_id, date, from_amount, to_amount) "
                "VALUES (:p, :f, :t, '2026-02-08', :a, :a)"
            ),
            {"p": pot, "f": main, "t": other, "a": figures["transfer_out"]},
        )
        await s.commit()

    yield {
        "users": users,
        "seats": seats,
        "group": group,
        "pot": pot,
        "main": main,
        "other": other,
        "sessionmaker": app_sessionmaker,
        "admin_sessionmaker": admin_sessionmaker,
    }

    async with admin_sessionmaker() as s:
        await _cleanup(s)
        await s.commit()
    await app_engine.dispose()
    await admin_engine.dispose()


# Order matters: every pot_id FK is ON DELETE RESTRICT, so the holdings go before the pot and the pot
# before its group. That ordering IS the safety property relied on elsewhere.
async def _cleanup(s: AsyncSession) -> None:
    groups = f"SELECT id FROM groups WHERE name = '{_GROUP}'"
    pots = f"SELECT id FROM pots WHERE group_id IN ({groups})"
    accounts = f"SELECT id FROM accounts WHERE pot_id IN ({pots})"
    await s.execute(text(f"DELETE FROM account_reconciliations WHERE account_id IN ({accounts})"))
    await s.execute(text(f"DELETE FROM expense_entries WHERE account_id IN ({accounts})"))
    await s.execute(text(f"DELETE FROM income_entries WHERE account_id IN ({accounts})"))
    await s.execute(text(f"DELETE FROM shared_expenses WHERE group_id IN ({groups})"))
    await s.execute(text(f"DELETE FROM shared_income WHERE group_id IN ({groups})"))
    await s.execute(text(f"DELETE FROM group_settlements WHERE group_id IN ({groups})"))
    await s.execute(text(f"DELETE FROM transfers WHERE pot_id IN ({pots})"))
    await s.execute(text(f"DELETE FROM pot_ownership_events WHERE pot_id IN ({pots})"))
    await s.execute(text(f"DELETE FROM shared_audit_log WHERE group_id IN ({groups})"))
    await s.execute(text(f"DELETE FROM accounts WHERE pot_id IN ({pots})"))
    await s.execute(text(f"DELETE FROM pots WHERE id IN ({pots})"))
    await s.execute(text(f"DELETE FROM groups WHERE name = '{_GROUP}'"))
    await s.execute(text("DELETE FROM users WHERE email = ANY(:e)"), {"e": list(_EMAILS.values())})


# Opens a restricted-role session with the per-request user context set to one seeded user. Importing
# app.db registers the after_begin listener that applies the id as a GUC, so these exercise the real
# isolation mechanism rather than a reimplementation of it.
def _as(seeded, key: str) -> AsyncSession:
    session = seeded["sessionmaker"]()
    set_session_user(session, seeded["users"][key])
    return session


# The account row as the service loads it, read through the app role so RLS applies.
async def _load_account(session: AsyncSession, account_id: int):
    from app.repositories import account_repository

    return await account_repository.get_by_id_any_scope(session, account_id)


class TestWhichRowTheLockCanBeTakenOn:
    @pytest.mark.asyncio
    async def test_a_read_only_co_owner_can_lock_the_pot(self, seeded):
        # pots_scope_write's USING is `app_can_view_pot(id) AND app_is_group_member(group_id)`, which
        # admits a read-only seat on purpose. That is what makes the pot's row a lock every member who
        # may reconcile can actually take.
        async with _as(seeded, "viewer") as s:
            locked = (await s.execute(text("SELECT id FROM pots WHERE id = :p FOR UPDATE"), {"p": seeded["pot"]})).scalars().all()
        assert locked == [seeded["pot"]]

    @pytest.mark.asyncio
    async def test_the_same_seat_cannot_lock_the_ACCOUNT_row_and_fails_by_returning_nothing(self, seeded):
        # The finding this whole decision rests on. accounts_scope_write requires pot WRITE access, and
        # a locking read applies the UPDATE policy's USING clause — so this matches no row and takes no
        # lock. It does not raise: RLS refuses by FILTERING, which is exactly why locking the account
        # here would have been a serialisation that silently was not one.
        async with _as(seeded, "viewer") as s:
            locked = (await s.execute(text("SELECT id FROM accounts WHERE id = :a FOR UPDATE"), {"a": seeded["main"]})).scalars().all()
        assert locked == []

    @pytest.mark.asyncio
    async def test_the_viewer_can_still_READ_that_account(self, seeded):
        # The positive control that makes the assertion above mean something: "0 rows" is equally true
        # of a wrong id, so this proves the row exists and is visible to this seat under SELECT.
        async with _as(seeded, "viewer") as s:
            visible = (await s.execute(text("SELECT id FROM accounts WHERE id = :a"), {"a": seeded["main"]})).scalars().all()
        assert visible == [seeded["main"]]

    @pytest.mark.asyncio
    async def test_a_writer_can_lock_the_account_row(self, seeded):
        # And the other direction, which pins the cause on the WRITE predicate rather than on anything
        # about the row itself.
        async with _as(seeded, "writer") as s:
            locked = (await s.execute(text("SELECT id FROM accounts WHERE id = :a FOR UPDATE"), {"a": seeded["main"]})).scalars().all()
        assert locked == [seeded["main"]]


class TestTheBalanceIsTheSameSumOverSources:
    @pytest.mark.asyncio
    async def test_both_derivations_agree_over_every_source_that_reaches_a_pots_account(self, seeded):
        # TWO DERIVATIONS, ONE FACT, over a POT's account and against a real database. The unit suite
        # pins the enumeration with mocked sums, which cannot notice that a pot's account resolves its
        # scope differently in each — one bounds by the ACCOUNT's owner (NULL here) and the other by the
        # CALLER's id, and they agree only because of what the tables can hold.
        async with _as(seeded, "writer") as s:
            account = await _load_account(s, seeded["main"])
            dated = await account_reconciliation_service.compute_account_balance_at(s, account, date(2026, 12, 31))
            live = await account_service.get_account_balances(s, [account], seeded["users"]["writer"])
        assert dated == live[seeded["main"]] == _EXPECTED_BALANCE

    @pytest.mark.asyncio
    async def test_the_figure_is_the_same_for_a_read_only_co_owner(self, seeded):
        # A shared account's balance must not depend on who is asking. It is the property the whole
        # scope-free-sum design exists for, and the one a caller-scoped predicate quietly breaks.
        async with _as(seeded, "viewer") as s:
            account = await _load_account(s, seeded["main"])
            dated = await account_reconciliation_service.compute_account_balance_at(s, account, date(2026, 12, 31))
            live = await account_service.get_account_balances(s, [account], seeded["users"]["viewer"])
        assert dated == live[seeded["main"]] == _EXPECTED_BALANCE

    @pytest.mark.asyncio
    async def test_every_source_moves_the_answer(self, seeded):
        # Proving the figure above discriminates rather than merely being reproducible: each source
        # carries a distinct amount, so the total can only be reached by counting all eight with the
        # right signs. Stated as an independent computation rather than by calling the formula twice.
        assert _EXPECTED_BALANCE == Decimal("1000.00") + Decimal("70.00") - Decimal("14.00") - Decimal("21.00") + Decimal("28.00") + Decimal(
            "35.00"
        ) - Decimal("42.00") + Decimal("49.00") - Decimal("56.00")
        assert len({amount for _n, amount, _s in _SOURCES}) == len(_SOURCES)

    @pytest.mark.asyncio
    async def test_a_private_row_naming_this_account_splits_the_two_answers(self, seeded):
        # The row my reasoning called impossible, constructed — and the layer that actually refuses it
        # named. A private expense naming a pot-owned account is refused by ensure_private_funding in
        # every service path and by NOTHING in the database, so this inserts one directly.
        #
        # The two derivations then DISAGREE by the whole amount: compute_account_balance_at bounds the
        # expense sum by the ACCOUNT's owner (NULL, so nothing matches) while get_account_balances bounds
        # it by the CALLER's (whose row it is). So the agreement proven above is not a property of these
        # two functions — it is a property of what ensure_private_funding lets exist, and that guard is
        # load-bearing rather than decorative.
        async with seeded["admin_sessionmaker"]() as admin:
            await admin.execute(
                text("INSERT INTO expense_entries (user_id, date, amount, currency, account_id) VALUES (:u, '2026-03-01', 9.00, 'ARS', :a)"),
                {"u": seeded["users"]["writer"], "a": seeded["main"]},
            )
            await admin.commit()

        async with _as(seeded, "writer") as s:
            account = await _load_account(s, seeded["main"])
            dated = await account_reconciliation_service.compute_account_balance_at(s, account, date(2026, 12, 31))
            live = await account_service.get_account_balances(s, [account], seeded["users"]["writer"])

        assert dated == _EXPECTED_BALANCE
        assert live[seeded["main"]] == _EXPECTED_BALANCE - Decimal("9.00")


class TestTheLatestReconciledDateIsScopeAware:
    @pytest.mark.asyncio
    async def test_a_co_owner_reads_the_pots_own_reconciliation(self, seeded):
        # The read that backs both the "last reconciled" column and the ordering guard that refuses an
        # out-of-order reconciliation. A bare owner match reads NULL against a shared row's NULL user_id
        # and answers "never reconciled" to everybody — which on the guard's side would let a member
        # post one underneath an existing one and skew it.
        async with seeded["admin_sessionmaker"]() as admin:
            await admin.execute(
                text(
                    "INSERT INTO account_reconciliations "
                    "(account_id, pot_id, as_of_date, statement_balance, computed_balance, difference, created_by) "
                    "VALUES (:a, :p, '2026-06-01', 10, 10, 0, :u)"
                ),
                {"a": seeded["main"], "p": seeded["pot"], "u": seeded["users"]["writer"]},
            )
            await admin.commit()

        for key in ("writer", "viewer"):
            async with _as(seeded, key) as s:
                latest = await account_reconciliation_repository.get_latest_dates_by_account_ids(s, [seeded["main"]], seeded["users"][key])
            assert latest[seeded["main"]].isoformat() == "2026-06-01", key

    @pytest.mark.asyncio
    async def test_an_account_with_no_reconciliation_is_simply_absent(self, seeded):
        # The positive control's mirror: without it, a query returning nothing for everything would pass
        # the test above in a world where the fixture id was wrong.
        async with _as(seeded, "writer") as s:
            latest = await account_reconciliation_repository.get_latest_dates_by_account_ids(s, [seeded["other"]], seeded["users"]["writer"])
        assert latest == {}


class TestTheAdjustmentPair:
    @pytest.mark.asyncio
    async def test_a_pots_reconciliation_may_not_carry_a_private_adjustment(self, seeded):
        # Stated as a CHECK rather than left to the service so it holds for the privileged session too,
        # and so a row read back says which kind of adjustment to look for from its scope alone.
        async with seeded["admin_sessionmaker"]() as admin:
            entry = (
                await admin.execute(
                    text("INSERT INTO expense_entries (user_id, date, amount, currency) VALUES (:u, '2026-03-01', 5, 'ARS') RETURNING id"),
                    {"u": seeded["users"]["writer"]},
                )
            ).scalar_one()
            with pytest.raises(IntegrityError):
                await admin.execute(
                    text(
                        "INSERT INTO account_reconciliations "
                        "(account_id, pot_id, as_of_date, statement_balance, computed_balance, difference, adjustment_expense_id) "
                        "VALUES (:a, :p, '2026-06-01', 5, 10, -5, :e)"
                    ),
                    {"a": seeded["main"], "p": seeded["pot"], "e": entry},
                )
            await admin.rollback()

    @pytest.mark.asyncio
    async def test_a_private_reconciliation_may_not_carry_a_shared_adjustment(self, seeded):
        # The other direction of the same pair. Both are needed: one CHECK would leave the column's
        # meaning depending on which scope happened to write it.
        async with seeded["admin_sessionmaker"]() as admin:
            shared = (
                await admin.execute(
                    text(
                        "INSERT INTO shared_expenses (group_id, date, amount, currency, split_method) "
                        "VALUES (:g, '2026-03-01', 5, 'ARS', 'equal') RETURNING id"
                    ),
                    {"g": seeded["group"]},
                )
            ).scalar_one()
            private_account = (
                await admin.execute(
                    text(
                        "INSERT INTO accounts (user_id, created_by, name, type, currency, opening_date) "
                        "VALUES (:u, :u, 'recon_private', 'bank', 'ARS', '2026-01-01') RETURNING id"
                    ),
                    {"u": seeded["users"]["writer"]},
                )
            ).scalar_one()
            with pytest.raises(IntegrityError):
                await admin.execute(
                    text(
                        "INSERT INTO account_reconciliations "
                        "(account_id, user_id, as_of_date, statement_balance, computed_balance, difference, adjustment_shared_expense_id) "
                        "VALUES (:a, :u, '2026-06-01', 5, 10, -5, :e)"
                    ),
                    {"a": private_account, "u": seeded["users"]["writer"], "e": shared},
                )
            await admin.rollback()
            # Cleaned up here rather than in _cleanup: this account hangs off no pot, so the group-scoped
            # teardown cannot reach it.
            await admin.execute(text("DELETE FROM accounts WHERE name = 'recon_private'"))
            await admin.commit()

    @pytest.mark.asyncio
    async def test_deleting_the_reconciliation_takes_its_shared_expense_and_its_splits(self, seeded):
        # The escape hatch for a mistyped statement balance, and the reason the FK is CASCADE from the
        # flow row's side. The SPLITS are asserted separately because they cascade from a different FK:
        # a member left holding a position in an expense that no longer exists would not be visible in a
        # count of expenses.
        async with seeded["admin_sessionmaker"]() as admin:
            reconciliation = (
                await admin.execute(
                    text(
                        "INSERT INTO account_reconciliations "
                        "(account_id, pot_id, as_of_date, statement_balance, computed_balance, difference, created_by) "
                        "VALUES (:a, :p, '2026-06-01', 5, 10, -5, :u) RETURNING id"
                    ),
                    {"a": seeded["main"], "p": seeded["pot"], "u": seeded["users"]["writer"]},
                )
            ).scalar_one()
            expense = (
                await admin.execute(
                    text(
                        "INSERT INTO shared_expenses "
                        "(group_id, date, amount, currency, split_method, paid_from_account_id, account_reconciliation_id) "
                        "VALUES (:g, '2026-06-01', 5, 'ARS', 'percentage', :a, :r) RETURNING id"
                    ),
                    {"g": seeded["group"], "a": seeded["main"], "r": reconciliation},
                )
            ).scalar_one()
            await admin.execute(
                text(
                    "INSERT INTO shared_expense_splits (shared_expense_id, group_id, member_id, amount, paid_amount) "
                    "VALUES (:e, :g, :m, 3, 3), (:e, :g, :m2, 2, 2)"
                ),
                {"e": expense, "g": seeded["group"], "m": seeded["seats"]["writer"], "m2": seeded["seats"]["viewer"]},
            )
            await admin.commit()

            assert await _count(admin, "shared_expense_splits", "shared_expense_id", expense) == 2

            await admin.execute(text("DELETE FROM account_reconciliations WHERE id = :r"), {"r": reconciliation})
            await admin.commit()

            assert await _count(admin, "shared_expenses", "id", expense) == 0
            assert await _count(admin, "shared_expense_splits", "shared_expense_id", expense) == 0


class TestOneReconciliationPerDate:
    @pytest.mark.asyncio
    async def test_a_pots_account_cannot_hold_two_reconciliations_on_one_date_either(self, seeded):
        # The UNIQUE constraint is on (account_id, as_of_date) and carries no scope term, which is what
        # makes re-reconciling a date a REPLACE on both sides. A pot's account is the one that would hurt
        # most if it did not: two rows on one date were both deletable by the date-comparing guard, and
        # dropping the older one took a SHARED adjustment out of every co-owner's share while the
        # survivor kept claiming a balance built on top of it.
        #
        # Asserted through the ADMIN session, so the refusal is the constraint's and not a policy's.
        async with seeded["admin_sessionmaker"]() as admin:
            insert = text(
                "INSERT INTO account_reconciliations (account_id, pot_id, as_of_date, statement_balance, computed_balance, difference) "
                "VALUES (:a, :p, '2026-06-01', 10, 10, 0) RETURNING id"
            )
            params = {"a": seeded["main"], "p": seeded["pot"]}
            first = (await admin.execute(insert, params)).scalar_one()
            with pytest.raises(IntegrityError) as exc:
                await admin.execute(insert, params)
            assert "account_reconciliations_account_date_key" in str(exc.value)
            await admin.rollback()

            # A different date is still free — the constraint is per date, not per account.
            await admin.execute(
                text(
                    "INSERT INTO account_reconciliations (account_id, pot_id, as_of_date, statement_balance, computed_balance, difference) "
                    "VALUES (:a, :p, '2026-06-02', 10, 10, 0)"
                ),
                params,
            )
            await admin.execute(text("DELETE FROM account_reconciliations WHERE account_id = :a"), {"a": seeded["main"]})
            await admin.commit()
            assert first is not None


async def _count(session: AsyncSession, table: str, column: str, value: int) -> int:
    return (await session.execute(text(f"SELECT count(*) FROM {table} WHERE {column} = :v"), {"v": value})).scalar_one()


# Who may WRITE one of these rows, which is the half the live walk found disagreeing with the service.
#
# account_reconciliations was the one dual-scope table whose FOR ALL policy named app_can_write_pot,
# and reconciling is gated on VISIBILITY — so a read-only co-owner passed every check in Python and was
# then refused by the database with a bare "new row violates row-level security policy". Two halves of
# one rule, disagreeing, and only a second logged-in account could show it.
class TestWhoMayWriteOne:
    @pytest.mark.asyncio
    async def test_a_read_only_co_owner_may_insert_one(self, seeded):
        # The defect, as a regression guard. This is the whole point of the decision: reconciling needs
        # only to SEE the pot, because the equivalent manual act — a shared expense drawn from that same
        # account — needs only group membership and a visible, divided pot.
        async with _as(seeded, "viewer") as s:
            await s.execute(
                text(
                    "INSERT INTO account_reconciliations "
                    "(account_id, pot_id, as_of_date, statement_balance, computed_balance, difference, created_by) "
                    "VALUES (:a, :p, '2026-07-01', 5, 10, -5, :u)"
                ),
                {"a": seeded["main"], "p": seeded["pot"], "u": seeded["users"]["viewer"]},
            )
            await s.commit()
        assert await _reconciliation_count(seeded) == 1

    @pytest.mark.asyncio
    async def test_a_read_only_co_owner_may_delete_one(self, seeded):
        # Deleting is that act's undo, gated identically. Postgres has no WITH CHECK for DELETE, so this
        # is its own policy rather than a clause on a FOR ALL — which is exactly the trap the rest of
        # this schema's two-policy split exists to avoid.
        async with seeded["admin_sessionmaker"]() as admin:
            await admin.execute(
                text(
                    "INSERT INTO account_reconciliations "
                    "(account_id, pot_id, as_of_date, statement_balance, computed_balance, difference, created_by) "
                    "VALUES (:a, :p, '2026-07-01', 5, 10, -5, :u)"
                ),
                {"a": seeded["main"], "p": seeded["pot"], "u": seeded["users"]["writer"]},
            )
            await admin.commit()

        async with _as(seeded, "viewer") as s:
            await s.execute(text("DELETE FROM account_reconciliations WHERE account_id = :a"), {"a": seeded["main"]})
            await s.commit()
        assert await _reconciliation_count(seeded) == 0

    @pytest.mark.asyncio
    async def test_the_column_grant_caps_what_an_update_may_touch(self, seeded):
        # Admitting a read-only seat to UPDATE was necessary — the service patches its own back-pointer
        # right after inserting — and admitting them to the WHOLE row would let them rewrite a statement
        # balance somebody else recorded, leaving the reconciliation claiming a difference its adjustment
        # does not match. RLS filters rows and never columns, so only the column grant can say this.
        #
        # The two refusals also fail DIFFERENTLY, which is worth seeing: a policy refuses by returning
        # "nothing changed", a grant raises.
        async with seeded["admin_sessionmaker"]() as admin:
            row = (
                await admin.execute(
                    text(
                        "INSERT INTO account_reconciliations "
                        "(account_id, pot_id, as_of_date, statement_balance, computed_balance, difference, created_by) "
                        "VALUES (:a, :p, '2026-07-01', 5, 10, -5, :u) RETURNING id"
                    ),
                    {"a": seeded["main"], "p": seeded["pot"], "u": seeded["users"]["writer"]},
                )
            ).scalar_one()
            await admin.commit()

        async with _as(seeded, "viewer") as s:
            with pytest.raises(ProgrammingError):
                await s.execute(text("UPDATE account_reconciliations SET statement_balance = 999 WHERE id = :r"), {"r": row})
            await s.rollback()

        # The positive control, and the thing the service actually does: the back-pointer IS writable.
        async with _as(seeded, "viewer") as s:
            await s.execute(
                text("UPDATE account_reconciliations SET adjustment_shared_expense_id = NULL WHERE id = :r"),
                {"r": row},
            )
            await s.commit()

        async with seeded["admin_sessionmaker"]() as admin:
            balance = (await admin.execute(text("SELECT statement_balance FROM account_reconciliations WHERE id = :r"), {"r": row})).scalar_one()
            assert balance == Decimal("5.00")
            await admin.execute(text("DELETE FROM account_reconciliations WHERE id = :r"), {"r": row})
            await admin.commit()


async def _reconciliation_count(seeded) -> int:
    async with seeded["admin_sessionmaker"]() as admin:
        return await _count(admin, "account_reconciliations", "account_id", seeded["main"])


# The query behind `can_reconcile`, driven against a real database.
#
# A mutation replacing its whole body with `return set(pot_ids)` — "every pot you asked about is
# divided" — killed no test, because every unit test of the accounts list stubs this function. That is
# the shape the skill warns about: a predicate whose wrong answer is not a crash but a row offering an
# action the endpoint then refuses, which is the exact picker-and-write disagreement one refusal rule
# exists to prevent.
class TestWhichPotsCountAsDivided:
    @pytest.mark.asyncio
    async def test_it_answers_only_the_pots_that_have_a_ledger(self, seeded):
        # Two pots asked about at once, one divided and one not, so the answer discriminates rather
        # than being reproducible: `set(pot_ids)` and `set()` are both wrong here, in opposite
        # directions, and only the real query returns exactly one of the two.
        async with seeded["admin_sessionmaker"]() as admin:
            undivided = (
                await admin.execute(
                    text("INSERT INTO pots (group_id, name, base_currency) VALUES (:g, 'recon_undivided', 'ARS') RETURNING id"),
                    {"g": seeded["group"]},
                )
            ).scalar_one()
            await admin.commit()

        try:
            async with seeded["admin_sessionmaker"]() as s:
                divided = await pot_ownership_repository.divided_pot_ids(s, [seeded["pot"], undivided])
            assert divided == {seeded["pot"]}
        finally:
            async with seeded["admin_sessionmaker"]() as admin:
                await admin.execute(text("DELETE FROM pots WHERE id = :p"), {"p": undivided})
                await admin.commit()

    @pytest.mark.asyncio
    async def test_an_empty_request_costs_no_query(self, seeded):
        # The early return every solo user's accounts list takes: no shared rows means no pot ids, and
        # the list must not pay a query to be told so.
        async with seeded["admin_sessionmaker"]() as s:
            assert await pot_ownership_repository.divided_pot_ids(s, []) == set()

    @pytest.mark.asyncio
    async def test_the_refusal_rule_reads_it_the_way_the_list_does(self, seeded):
        # The two halves joined: the query's answer fed straight into the rule the WRITE raises from.
        # Without this the query and the rule are each tested against their own idea of the other.
        async with seeded["admin_sessionmaker"]() as s:
            divided = await pot_ownership_repository.divided_pot_ids(s, [seeded["pot"]])
        assert reconciliation_refusal(seeded["pot"], divided) is None
        assert isinstance(reconciliation_refusal(seeded["pot"], set()), AccountReconciliationPotNotDividedError)
