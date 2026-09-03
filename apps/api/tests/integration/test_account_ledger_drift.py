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
from app.domain.account_movement import MovementKind, MovementSource
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

    # A group both users hold a seat in, with a pot holding one joint account. Present so the movement
    # kinds the flow half and the ownership ledger add have somewhere to happen: a shared expense drawn
    # from a private account, shared income arriving in one, a settlement between the two seats, and a
    # contribution crossing the scope boundary.
    group = await scalar("INSERT INTO groups (name, kind, created_by) VALUES ('Ledger group', 'household', :u) RETURNING id", u=users[0])
    seats = [
        await scalar(
            "INSERT INTO group_members (group_id, user_id, display_name, role) VALUES (:g, :u, 'A', 'admin') RETURNING id", g=group, u=users[0]
        ),
        await scalar(
            "INSERT INTO group_members (group_id, user_id, display_name, role) VALUES (:g, :u, 'B', 'member') RETURNING id", g=group, u=users[1]
        ),
    ]
    pot = await scalar(
        "INSERT INTO pots (group_id, base_currency, is_default) VALUES (:g, 'ARS', TRUE) RETURNING id",
        g=group,
    )

    async def pot_account(name: str, opening: Decimal):
        return await scalar(
            "INSERT INTO accounts (pot_id, name, type, currency, opening_balance, opening_date) VALUES (:p, :n, 'bank', 'ARS', :b, :d) RETURNING id",
            p=pot,
            n=name,
            b=opening,
            d=_OPENING,
        )

    # TWO of the pot's accounts, not one: a transfer has to stay within a single scope (§4.1), so a
    # pot-scoped transfer needs a second pot account to reach — and one joint account could not tell a
    # scope-aware transfer branch from an owner-only one.
    joint = await pot_account("Joint", Decimal("0.00"))
    joint_two = await pot_account("Joint savings", Decimal("8000.00"))
    return {
        "users": users,
        "ars": ars,
        "usd": usd,
        "other": other,
        "card": card,
        "group": group,
        "seats": seats,
        "pot": pot,
        "joint": joint,
        "joint_two": joint_two,
    }


# Asserts the ledger's own sum and the accounts page's balance agree for the given account.
#
# The row is loaded in EITHER scope, because a pot's account has no owner at all and is still an
# account whose ledger has to add up. `user_id` stays the ASKER's: it scopes the private-entry branches,
# which are always empty for a shared account, and passing it is what lets the same assertion run for
# two different callers on one shared row.
#
# The account's `pot_id` goes in too, and it is load-bearing rather than tidy: `transfers` is the one
# movement table that carries a scope of its own, so a transfer between two of a pot's accounts is
# matched by the balance sums (which compare against the joined account's pot) and would be invisible
# to a ledger filtering on the asker's user_id alone.
async def _assert_no_drift(session: AsyncSession, account_id: int, user_id: int):
    account = await account_repository.get_by_id_any_scope(session, account_id)
    from_balance_path = await account_service.get_account_balance(session, account, user_id)
    from_union = await account_movement_repository.sum_movements(
        session, account_id, user_id, opening_date=account.opening_date, pot_id=account.pot_id
    )
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
    async def test_a_cross_currency_settlement_reaches_the_balance_by_its_account_leg(self, session, fixtures):
        # The case this whole feature turns on, and the one most able to drift: a USD bucket paid from a
        # PESO account. `amount` clears the card in USD; `account_amount` is what actually left the
        # account. Three separate sums read the cash leg (live balance, point-in-time, monthly chart) plus
        # the ledger union — if ANY of them summed `amount` instead, the account would lose 100 rather
        # than 130,000 and this assertion is what says so.
        u, ars, card = fixtures["users"][0], fixtures["ars"], fixtures["card"]
        await session.execute(
            text(
                "INSERT INTO card_settlements (credit_card_id, user_id, date, amount, currency, account_id, account_amount)"
                " VALUES (:c, :u, '2026-07-18', 100, 'USD', :a, 130000)"
            ),
            {"c": card, "u": u, "a": ars},
        )
        await session.flush()

        assert await _assert_no_drift(session, ars, u) == _OPENING_BALANCE - Decimal("130000.00")

    @pytest.mark.asyncio
    async def test_a_same_currency_settlement_still_sums_its_only_amount(self, session, fixtures):
        # account_amount NULL means no conversion happened, so the coalesce must fall back to `amount`.
        # Every settlement that existed before this feature is exactly this shape.
        u, ars, card = fixtures["users"][0], fixtures["ars"], fixtures["card"]
        await session.execute(
            text(
                "INSERT INTO card_settlements (credit_card_id, user_id, date, amount, currency, account_id, account_amount)"
                " VALUES (:c, :u, '2026-07-18', 8000, 'ARS', :a, NULL)"
            ),
            {"c": card, "u": u, "a": ars},
        )
        await session.flush()

        assert await _assert_no_drift(session, ars, u) == _OPENING_BALANCE - Decimal("8000.00")

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


class TestTheScopeCrossingMovements:
    """The three kinds that reach an account without being an income, an expense or a transfer.

    Each was, or would have been, invisible to the ledger while counting in the balance — which reads
    on the account page as a figure no visible row explains, and as a wrong `balance_after` on every
    row above it. The ownership case was a REAL defect on main before this PR: measured on a live
    database, an account with 100,000 opening and one 5,000 contribution reported 95,000 from the
    balance and 100,000 from the ledger.
    """

    @pytest.mark.asyncio
    async def test_a_contribution_leaves_the_private_account_and_arrives_in_the_pots(self, session, fixtures):
        u, ars, joint, pot, seat = fixtures["users"][0], fixtures["ars"], fixtures["joint"], fixtures["pot"], fixtures["seats"][0]
        await session.execute(
            text(
                "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, units, unit_price, base_amount)"
                " VALUES (:p, 'opening', '2026-07-02', :m, 100, 1, 100)"
            ),
            {"p": pot, "m": seat},
        )
        await session.execute(
            text(
                "INSERT INTO pot_ownership_events"
                " (pot_id, type, date, member_id, units, unit_price, amount, base_amount, from_account_id, to_account_id)"
                " VALUES (:p, 'contribution', '2026-07-20', :m, 50, 100, 5000, 5000, :f, :t)"
            ),
            {"p": pot, "m": seat, "f": ars, "t": joint},
        )
        await session.flush()

        assert await _assert_no_drift(session, ars, u) == _OPENING_BALANCE - Decimal("5000.00")
        # And the far leg, which is what makes the pot's value actually move.
        joint_account = await account_repository.get_by_id_any_scope(session, joint)
        assert (await account_service.get_account_balances(session, [joint_account], u))[joint] == Decimal("5000.00")

    @pytest.mark.asyncio
    async def test_a_cross_currency_contribution_moves_each_account_by_its_own_figure(self, session, fixtures):
        # The two legs are denominated DIFFERENTLY, and reading one column on both is the whole way
        # this goes wrong: a contribution runs private -> pot, so its `from` leg moves `amount` (the
        # private account's currency) and its `to` leg `base_amount` (the pot's).
        #
        # The same-currency case above cannot see it — there the two figures are equal, so a leg
        # reading the wrong column produces the right answer. A mutation sweep survived on exactly
        # that flatness, which is why this fixture makes them differ by three orders of magnitude.
        u, usd, joint, pot, seat = fixtures["users"][0], fixtures["usd"], fixtures["joint"], fixtures["pot"], fixtures["seats"][0]
        await session.execute(
            text(
                "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, units, unit_price, base_amount)"
                " VALUES (:p, 'opening', '2026-07-02', :m, 100, 1, 100)"
            ),
            {"p": pot, "m": seat},
        )
        # 40 dollars out of the USD account arriving as 60,000 pesos in the pot's ARS account.
        await session.execute(
            text(
                "INSERT INTO pot_ownership_events"
                " (pot_id, type, date, member_id, units, unit_price, amount, amount_currency, base_amount, from_account_id, to_account_id)"
                " VALUES (:p, 'contribution', '2026-07-20', :m, 600, 100, 40, 'USD', 60000, :f, :t)"
            ),
            {"p": pot, "m": seat, "f": usd, "t": joint},
        )
        await session.flush()

        # The private leg moved DOLLARS...
        assert await _assert_no_drift(session, usd, u) == Decimal("-40.00")
        # ...and the pot's leg PESOS. A leg reading the other column would show -60,000 and +40.
        joint_account = await account_repository.get_by_id_any_scope(session, joint)
        assert (await account_service.get_account_balances(session, [joint_account], u))[joint] == Decimal("60000.00")

        # And the LEDGER's own figure for the far leg, which the drift helper cannot reach: it reads
        # through the account service's owner-scoped lookup, and the pot's account has no owner. Without
        # this the incoming branch's CASE is unasserted — a mutation making both legs read the same
        # column survived on exactly that, because the outgoing leg happens to read it either way.
        rows, _ = await account_movement_repository.list_movements(session, joint, u, opening_date=_OPENING, pot_id=pot)
        arriving = next(row.movement for row in rows if row.movement.source == MovementSource.ownership)
        assert arriving.amount == Decimal("60000.00")
        # The pair IS the rate record, so the other side rides along rather than being derived.
        assert (arriving.counterparty_amount, arriving.counterparty_currency) == (Decimal("40.00"), "USD")

    @pytest.mark.asyncio
    async def test_a_transfer_between_two_of_a_pots_accounts_reaches_the_ledger(self, session, fixtures):
        # `transfers` is the ONE movement table that carries a scope of its own (§3), so this is the
        # only movement kind whose ledger branch can disagree with the balance sums beside it about
        # what a shared account holds. The balance compares against the joined account's pot; a branch
        # filtering on the asker's user_id alone sees nothing here, because a pot-scoped transfer has
        # user_id NULL — so the account's balance moved and its ledger did not say why.
        #
        # Asserted from BOTH accounts, since the two legs are separate branches and an outgoing-only
        # fix would leave the arriving side silent.
        u, pot, joint, joint_two = fixtures["users"][0], fixtures["pot"], fixtures["joint"], fixtures["joint_two"]
        await session.execute(
            text(
                "INSERT INTO transfers (pot_id, date, from_account_id, to_account_id, from_amount, to_amount)"
                " VALUES (:p, '2026-07-18', :f, :t, 3000, 3000)"
            ),
            {"p": pot, "f": joint_two, "t": joint},
        )
        await session.flush()

        assert await _assert_no_drift(session, joint_two, u) == Decimal("5000.00")
        assert await _assert_no_drift(session, joint, u) == Decimal("3000.00")

    @pytest.mark.asyncio
    async def test_a_shared_expense_takes_the_whole_amount_from_the_account_that_paid(self, session, fixtures):
        # The WHOLE amount, not the payer's share: the money really left. Who owed whom afterwards is
        # the splits' business and never the account's.
        u, ars, group, seats = fixtures["users"][0], fixtures["ars"], fixtures["group"], fixtures["seats"]
        expense = (
            await session.execute(
                text(
                    "INSERT INTO shared_expenses (group_id, date, amount, currency, category, split_method, paid_from_account_id)"
                    " VALUES (:g, '2026-07-12', 9000, 'ARS', 'dining', 'equal', :a) RETURNING id"
                ),
                {"g": group, "a": ars},
            )
        ).scalar_one()
        for seat, amount, paid in ((seats[0], 4500, 9000), (seats[1], 4500, 0)):
            await session.execute(
                text("INSERT INTO shared_expense_splits (shared_expense_id, group_id, member_id, amount, paid_amount) VALUES (:e, :g, :m, :a, :p)"),
                {"e": expense, "g": group, "m": seat, "a": amount, "p": paid},
            )
        await session.flush()

        assert await _assert_no_drift(session, ars, u) == _OPENING_BALANCE - Decimal("9000.00")

    @pytest.mark.asyncio
    async def test_shared_income_puts_the_whole_amount_into_the_account_that_received_it(self, session, fixtures):
        # The mirror of the shared expense above, and the sign is the point: the WHOLE amount arrives,
        # not the recipient's share. A branch that subtracted instead of adding would move the balance
        # by twice the figure in the wrong direction, and the ledger's own sum would agree with it —
        # which is exactly why this asserts the resulting BALANCE and not just the absence of drift.
        u, ars, group, seats = fixtures["users"][0], fixtures["ars"], fixtures["group"], fixtures["seats"]
        income = (
            await session.execute(
                text(
                    "INSERT INTO shared_income (group_id, date, amount, currency, category, split_method, destination, paid_to_account_id)"
                    " VALUES (:g, '2026-07-14', 6000, 'ARS', 'rental_income', 'equal', 'distributed', :a) RETURNING id"
                ),
                {"g": group, "a": ars},
            )
        ).scalar_one()
        for seat, entitled, received in ((seats[0], 3000, 6000), (seats[1], 3000, 0)):
            await session.execute(
                text("INSERT INTO shared_income_splits (shared_income_id, group_id, member_id, amount, received_amount) VALUES (:i, :g, :m, :a, :r)"),
                {"i": income, "g": group, "m": seat, "a": entitled, "r": received},
            )
        await session.flush()

        assert await _assert_no_drift(session, ars, u) == _OPENING_BALANCE + Decimal("6000.00")

    @pytest.mark.asyncio
    async def test_shared_income_into_a_POT_account_reads_the_same_for_every_member(self, session, fixtures):
        # The JOINT destination, and the property that matters about it: the account belongs to no user
        # at all, so its balance must not depend on who is asking. Neither the sum nor the ledger branch
        # carries a user filter, and driving BOTH members through the same assertion is the only thing
        # that proves it — a filter on either side would give one of them a different figure while
        # staying perfectly self-consistent for the other.
        users, joint, group, seats = fixtures["users"], fixtures["joint"], fixtures["group"], fixtures["seats"]
        income = (
            await session.execute(
                text(
                    "INSERT INTO shared_income (group_id, date, amount, currency, split_method, destination, paid_to_account_id)"
                    " VALUES (:g, '2026-07-15', 8000, 'ARS', 'equal', 'joint', :a) RETURNING id"
                ),
                {"g": group, "a": joint},
            )
        ).scalar_one()
        for seat, received in ((seats[0], 5000), (seats[1], 3000)):
            await session.execute(
                text(
                    "INSERT INTO shared_income_splits (shared_income_id, group_id, member_id, amount, received_amount) VALUES (:i, :g, :m, 4000, :r)"
                ),
                {"i": income, "g": group, "m": seat, "r": received},
            )
        await session.flush()

        # The joint account opens at zero (see the fixture), so the whole 8,000 is what arrived — the
        # WHOLE amount and not either member's share of it.
        assert await _assert_no_drift(session, joint, users[0]) == Decimal("8000.00")
        assert await _assert_no_drift(session, joint, users[1]) == Decimal("8000.00")

    @pytest.mark.asyncio
    async def test_a_pre_opening_shared_income_row_is_excluded_by_both(self, session, fixtures):
        # opening_balance IS the balance at opening_date, so an earlier row is already inside it. The
        # bound has to hold on BOTH sides or the ledger lists a row the balance does not count — and it
        # lives in a join on this side, which no mocked session can exercise.
        u, ars, group = fixtures["users"][0], fixtures["ars"], fixtures["group"]
        await session.execute(
            text(
                "INSERT INTO shared_income (group_id, date, amount, currency, split_method, destination, paid_to_account_id)"
                " VALUES (:g, '2026-06-01', 4000, 'ARS', 'equal', 'distributed', :a)"
            ),
            {"g": group, "a": ars},
        )
        await session.flush()

        assert await _assert_no_drift(session, ars, u) == _OPENING_BALANCE

    @pytest.mark.asyncio
    async def test_both_legs_of_a_settlement_move_real_cash(self, session, fixtures):
        # D15: settling MOVES money. The payer's account falls and the payee's rises, and a settlement
        # that only cleared a balance would leave both accounts stating figures nobody holds.
        users, ars, other, group, seats = fixtures["users"], fixtures["ars"], fixtures["other"], fixtures["group"], fixtures["seats"]
        await session.execute(
            text(
                "INSERT INTO group_settlements (group_id, from_member_id, to_member_id, date, amount, currency, from_account_id, to_account_id)"
                " VALUES (:g, :f, :t, '2026-07-18', 2500, 'ARS', :fa, :ta)"
            ),
            {"g": group, "f": seats[0], "t": seats[1], "fa": ars, "ta": other},
        )
        await session.flush()

        assert await _assert_no_drift(session, ars, users[0]) == _OPENING_BALANCE - Decimal("2500.00")
        assert await _assert_no_drift(session, other, users[1]) == Decimal("5000.00") + Decimal("2500.00")

    @pytest.mark.asyncio
    async def test_a_cross_currency_settlement_reaches_each_account_by_its_own_leg(self, session, fixtures):
        # The bucket is cleared in ARS while the money leaves a USD account. Reading `amount` on both
        # legs would take 2,500 pesos out of a dollar account.
        users, usd, other, group, seats = fixtures["users"], fixtures["usd"], fixtures["other"], fixtures["group"], fixtures["seats"]
        await session.execute(
            text(
                "INSERT INTO group_settlements"
                " (group_id, from_member_id, to_member_id, date, amount, currency, from_account_id, from_amount, to_account_id)"
                " VALUES (:g, :f, :t, '2026-07-18', 2500, 'ARS', :fa, 2, :ta)"
            ),
            {"g": group, "f": seats[0], "t": seats[1], "fa": usd, "ta": other},
        )
        await session.flush()

        assert await _assert_no_drift(session, usd, users[0]) == Decimal("-2.00")
        # The payee's side had no conversion, so it moves the bucket amount.
        assert await _assert_no_drift(session, other, users[1]) == Decimal("7500.00")

    @pytest.mark.asyncio
    async def test_a_written_off_balance_moves_no_cash_at_all(self, session, fixtures):
        # It clears the bucket and nothing else. A ledger row for a payment nobody made would have to
        # be a zero, or a lie.
        users, ars, group, seats = fixtures["users"], fixtures["ars"], fixtures["group"], fixtures["seats"]
        await session.execute(
            text(
                "INSERT INTO group_settlements (group_id, from_member_id, to_member_id, date, amount, currency, status)"
                " VALUES (:g, :f, :t, '2026-07-18', 2500, 'ARS', 'written_off')"
            ),
            {"g": group, "f": seats[0], "t": seats[1]},
        )
        await session.flush()

        assert await _assert_no_drift(session, ars, users[0]) == _OPENING_BALANCE

    @pytest.mark.asyncio
    async def test_a_pre_opening_shared_expense_is_excluded_by_both(self, session, fixtures):
        # opening_balance IS the balance at opening_date, so an earlier row is already inside it.
        # The bound has to hold on BOTH sides or the ledger lists a row the balance does not count.
        u, ars, group, seats = fixtures["users"][0], fixtures["ars"], fixtures["group"], fixtures["seats"]
        expense = (
            await session.execute(
                text(
                    "INSERT INTO shared_expenses (group_id, date, amount, currency, split_method, paid_from_account_id)"
                    " VALUES (:g, '2026-06-01', 4000, 'ARS', 'equal', :a) RETURNING id"
                ),
                {"g": group, "a": ars},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO shared_expense_splits (shared_expense_id, group_id, member_id, amount, paid_amount) VALUES (:e, :g, :m, 4000, 4000)"),
            {"e": expense, "g": group, "m": seats[0]},
        )
        await session.flush()

        assert await _assert_no_drift(session, ars, u) == _OPENING_BALANCE

    @pytest.mark.asyncio
    async def test_every_new_source_lands_on_the_kind_its_filter_promises(self, session, fixtures):
        # The ledger's kind filter is a partition: a row the unfiltered list shows and no filter
        # matches is a row the user cannot reach. Driven through the real filter rather than asserted
        # on the branch list, so a kind wired into the union but not into the dispatch reddens.
        u, ars, joint, pot, group, seats = (
            fixtures["users"][0],
            fixtures["ars"],
            fixtures["joint"],
            fixtures["pot"],
            fixtures["group"],
            fixtures["seats"],
        )
        expense = (
            await session.execute(
                text(
                    "INSERT INTO shared_expenses (group_id, date, amount, currency, split_method, paid_from_account_id)"
                    " VALUES (:g, '2026-07-12', 900, 'ARS', 'equal', :a) RETURNING id"
                ),
                {"g": group, "a": ars},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO shared_expense_splits (shared_expense_id, group_id, member_id, amount, paid_amount) VALUES (:e, :g, :m, 900, 900)"),
            {"e": expense, "g": group, "m": seats[0]},
        )
        await session.execute(
            text(
                "INSERT INTO group_settlements (group_id, from_member_id, to_member_id, date, amount, currency, from_account_id)"
                " VALUES (:g, :f, :t, '2026-07-18', 250, 'ARS', :a)"
            ),
            {"g": group, "f": seats[0], "t": seats[1], "a": ars},
        )
        await session.execute(
            text(
                "INSERT INTO pot_ownership_events"
                " (pot_id, type, date, member_id, units, unit_price, amount, base_amount, from_account_id, to_account_id)"
                " VALUES (:p, 'contribution', '2026-07-20', :m, 50, 100, 5000, 5000, :f, :t)"
            ),
            {"p": pot, "m": seats[0], "f": ars, "t": joint},
        )
        income = (
            await session.execute(
                text(
                    "INSERT INTO shared_income (group_id, date, amount, currency, split_method, destination, paid_to_account_id)"
                    " VALUES (:g, '2026-07-22', 700, 'ARS', 'equal', 'distributed', :a) RETURNING id"
                ),
                {"g": group, "a": ars},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO shared_income_splits (shared_income_id, group_id, member_id, amount, received_amount) VALUES (:i, :g, :m, 700, 700)"),
            {"i": income, "g": group, "m": seats[0]},
        )
        await session.flush()

        account = await account_repository.get_by_id(session, ars, u)
        unfiltered, _ = await account_movement_repository.list_movements(session, ars, u, opening_date=account.opening_date, page_size=100)
        by_kind: dict[str, int] = {}
        for kind in MovementKind:
            rows, _ = await account_movement_repository.list_movements(session, ars, u, opening_date=account.opening_date, kind=kind, page_size=100)
            by_kind[kind.value] = len(rows)
        assert {source.value for source in (m.movement.source for m in unfiltered)} == {
            "shared_expense",
            "shared_income",
            "group_settlement",
            "ownership",
        }
        assert by_kind["expense"] == 1 and by_kind["group_settlement"] == 1 and by_kind["ownership"] == 1
        assert by_kind["income"] == 1 and by_kind["adjustment"] == 0
        # And the KIND COLUMN each row carries, not merely which filter returned it. The two are
        # separate — the filter dispatch decides which branches run, the column decides what the row
        # says it is — so counting rows per filter left a row that reported itself as a
        # reconciliation adjustment perfectly satisfying the counts above. A sweep found that.
        kinds = {m.movement.source.value: m.movement.kind.value for m in unfiltered}
        assert kinds["shared_income"] == "income", kinds
        assert kinds["shared_expense"] == "expense" and kinds["ownership"] == "ownership"
        # And the CARD settlement kind stays what its shipped label says it is: no group row landed in it.
        assert by_kind["settlement"] == 0
        assert sum(by_kind.values()) == len(unfiltered)


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
