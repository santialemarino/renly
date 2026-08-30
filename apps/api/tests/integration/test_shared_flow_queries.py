import os
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# The three queries whose whole correctness lives in the SQL, driven against a real Postgres.
#
#   * the /expenses UNION — a mocked session cannot tell a union that returns the caller's share from
#     one that returns the whole expense, or one whose page order is not a total order;
#   * the balance AGGREGATION — two columns summed per member per currency, which a mock returns
#     whatever it was told for;
#   * the settlement LEG sums — the `coalesce(<leg>_amount, amount)` that decides whether a
#     cross-currency settlement moves the bucket's figure or the account's.
#
# Skipped unless LEDGER_TEST_DATABASE_URL points at a database with the schema applied, matching the
# contract the other query suites use.
from app.domain.shared_expense import apply_settlements, expense_positions, minimise_transfers
from app.repositories import expense_repository, group_settlement_repository, shared_expense_repository

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(DB_URL)
    async with AsyncSession(engine) as s:
        yield s
        await s.rollback()
    await engine.dispose()


# One group of three (two accounts, one placeholder), a private expense list for the first user, and
# three shared expenses in two currencies with a settlement against them. Enough that a union which
# returned the wrong column, ordered wrongly, or netted two currencies would show it.
@pytest_asyncio.fixture
async def seeded(session: AsyncSession):
    async def scalar(sql: str, **params):
        return (await session.execute(text(sql), params)).scalar_one()

    users = [
        await scalar("INSERT INTO users (name, email, password_hash) VALUES ('Q A', 'flowq_a@test.local', 'x') RETURNING id"),
        await scalar("INSERT INTO users (name, email, password_hash) VALUES ('Q B', 'flowq_b@test.local', 'x') RETURNING id"),
    ]
    group = await scalar("INSERT INTO groups (name, kind, created_by) VALUES ('Query group', 'household', :u) RETURNING id", u=users[0])
    seats = [
        await scalar(
            "INSERT INTO group_members (group_id, user_id, display_name, role) VALUES (:g, :u, 'A', 'admin') RETURNING id", g=group, u=users[0]
        ),
        await scalar(
            "INSERT INTO group_members (group_id, user_id, display_name, role) VALUES (:g, :u, 'B', 'member') RETURNING id", g=group, u=users[1]
        ),
        await scalar("INSERT INTO group_members (group_id, display_name) VALUES (:g, 'Placeholder') RETURNING id", g=group),
    ]
    account = await scalar(
        "INSERT INTO accounts (user_id, created_by, name, type, currency, opening_balance, opening_date)"
        " VALUES (:u, :u, 'A account', 'bank', 'ARS', 100000, '2026-01-01') RETURNING id",
        u=users[0],
    )
    usd_account = await scalar(
        "INSERT INTO accounts (user_id, created_by, name, type, currency, opening_balance, opening_date)"
        " VALUES (:u, :u, 'A dollars', 'bank', 'USD', 500, '2026-01-01') RETURNING id",
        u=users[0],
    )
    # The caller's own private rows, one of them sharing a date with a shared one.
    for day, amount in ((date(2026, 5, 1), 1000), (date(2026, 6, 1), 2000)):
        await session.execute(
            text("INSERT INTO expense_entries (user_id, date, amount, currency, category, notes) VALUES (:u, :d, :a, 'ARS', 'food', 'private')"),
            {"u": users[0], "d": day, "a": amount},
        )

    async def shared(day: date, amount: int, currency: str, splits: dict[int, tuple[int, int]], notes: str = "shared"):
        expense = await scalar(
            "INSERT INTO shared_expenses (group_id, date, amount, currency, category, split_method, notes)"
            " VALUES (:g, :d, :a, :c, 'dining', 'equal', :n) RETURNING id",
            g=group,
            d=day,
            a=amount,
            c=currency,
            n=notes,
        )
        for seat, (consumed, fronted) in splits.items():
            await session.execute(
                text("INSERT INTO shared_expense_splits (shared_expense_id, group_id, member_id, amount, paid_amount) VALUES (:e, :g, :m, :a, :p)"),
                {"e": expense, "g": group, "m": seat, "a": consumed, "p": fronted},
            )
        return expense

    # 9,000 ARS split three ways, fronted by seat A.
    await shared(date(2026, 6, 1), 9000, "ARS", {seats[0]: (3000, 9000), seats[1]: (3000, 0), seats[2]: (3000, 0)})
    # 60 USD, seat B fronts, only A and B take part — a second bucket that must never net with the first.
    await shared(date(2026, 6, 10), 60, "USD", {seats[0]: (30, 0), seats[1]: (30, 60)})
    # One where seat A took no part but fronted it (D33): a zero share that must not appear as spending.
    await shared(date(2026, 6, 15), 400, "ARS", {seats[0]: (0, 400), seats[1]: (400, 0)}, notes="not mine")
    await session.flush()
    return {"users": users, "group": group, "seats": seats, "account": account, "usd_account": usd_account}


class TestTheExpensesUnion:
    @pytest.mark.asyncio
    async def test_it_returns_the_callers_share_not_the_whole_expense(self, session, seeded):
        rows, total = await expense_repository.list_by_user_filtered(session, seeded["users"][0], [seeded["seats"][0]], page_size=50)
        shared = sorted((row.currency, row.amount, row.full_amount) for row in rows if row.scope == "shared")
        # The caller's SHARE beside the whole expense, in both buckets. A union returning `amount` from
        # the parent would report 9,000 and 60 here, which is what the group spent rather than what
        # this person did — D2's whole point, and invisible to any mocked session.
        assert shared == [("ARS", Decimal("3000.00"), Decimal("9000.00")), ("USD", Decimal("30.00"), Decimal("60.00"))]
        # Two private rows plus those two, and the total agrees with the page.
        assert total == len(rows) == 4

    @pytest.mark.asyncio
    async def test_a_zero_share_never_appears(self, session, seeded):
        # A payer who took no part holds a position in the expense but spent nothing on it, so it is
        # not spending and does not belong in a spending list.
        rows, _ = await expense_repository.list_by_user_filtered(session, seeded["users"][0], [seeded["seats"][0]], page_size=50)
        assert all(row.notes != "not mine" for row in rows)

    @pytest.mark.asyncio
    async def test_a_user_in_no_group_sees_only_their_own(self, session, seeded):
        rows, total = await expense_repository.list_by_user_filtered(session, seeded["users"][0], [], page_size=50)
        assert {row.scope for row in rows} == {"private"}
        assert total == 2

    @pytest.mark.asyncio
    async def test_paging_never_repeats_or_drops_a_row(self, session, seeded):
        # The reason the tie-break carries the scope: ids are unique per TABLE and this list spans two.
        seen: list[tuple[str, int]] = []
        page = 1
        while True:
            rows, total = await expense_repository.list_by_user_filtered(session, seeded["users"][0], [seeded["seats"][0]], page=page, page_size=1)
            if not rows:
                break
            seen.extend((row.scope, row.id) for row in rows)
            if len(seen) >= total:
                break
            page += 1
        assert len(set(seen)) == len(seen) == 4

    @pytest.mark.asyncio
    async def test_a_filter_narrows_both_branches_together(self, session, seeded):
        rows, _ = await expense_repository.list_by_user_filtered(
            session, seeded["users"][0], [seeded["seats"][0]], date_from=date(2026, 6, 1), date_to=date(2026, 6, 1), page_size=50
        )
        # One private and one shared row share that date, so a filter that reached only one branch
        # would return one row rather than two.
        assert sorted(row.scope for row in rows) == ["private", "shared"]

    @pytest.mark.asyncio
    async def test_sorting_by_amount_orders_across_the_union(self, session, seeded):
        rows, _ = await expense_repository.list_by_user_filtered(
            session, seeded["users"][0], [seeded["seats"][0]], sort_by="amount", sort_order="desc", page_size=50
        )
        assert [row.amount for row in rows] == sorted((row.amount for row in rows), reverse=True)


class TestTheBalanceAggregation:
    @pytest.mark.asyncio
    async def test_positions_come_back_per_currency_per_member(self, session, seeded):
        rows = [row[1:] for row in await shared_expense_repository.list_positions_by_groups(session, [seeded["group"]])]
        by_key = {(currency, member_id): (consumed, fronted) for currency, member_id, consumed, fronted in rows}
        # Seat A: 3,000 consumed of the dinner and 400 fronted of the one they took no part in.
        assert by_key[("ARS", seeded["seats"][0])] == (Decimal("3000.00"), Decimal("9400.00"))
        assert by_key[("USD", seeded["seats"][1])] == (Decimal("30.00"), Decimal("60.00"))

    @pytest.mark.asyncio
    async def test_every_bucket_sums_to_zero(self, session, seeded):
        # THE invariant, over real rows this time rather than a generated corpus.
        rows = [row[1:] for row in await shared_expense_repository.list_positions_by_groups(session, [seeded["group"]])]
        movements = [row[1:] for row in await group_settlement_repository.list_movements_by_groups(session, [seeded["group"]])]
        for currency in {row[0] for row in rows}:
            positions = expense_positions([(member_id, consumed, fronted) for c, member_id, consumed, fronted in rows if c == currency])
            net = apply_settlements(positions, [(f, t, a) for c, f, t, a in movements if c == currency])
            assert sum(net.values(), Decimal(0)) == Decimal(0), currency
            # And the plan derived from it clears the bucket exactly.
            moved = [(t.from_member_id, t.to_member_id, t.amount) for t in minimise_transfers(net)]
            assert apply_settlements(net, moved) == {}

    @pytest.mark.asyncio
    async def test_a_settlement_moves_the_bucket_it_names_and_no_other(self, session, seeded):
        await session.execute(
            text(
                "INSERT INTO group_settlements (group_id, from_member_id, to_member_id, date, amount, currency)"
                " VALUES (:g, :f, :t, '2026-06-20', 3000, 'ARS')"
            ),
            {"g": seeded["group"], "f": seeded["seats"][1], "t": seeded["seats"][0]},
        )
        await session.flush()
        movements = [row[1:] for row in await group_settlement_repository.list_movements_by_groups(session, [seeded["group"]])]
        assert [row[0] for row in movements] == ["ARS"]


class TestTheCardBucketGrouping:
    # A card's liability is per CURRENCY bucket, and the grouping into those buckets happens in the
    # repository — which a unit test stubs, so only a real query exercises it. A group can also open a
    # bucket the card has never seen, which is what the second currency below is for.
    @pytest.mark.asyncio
    async def test_a_cards_group_charges_come_back_grouped_by_currency(self, session, seeded):
        card = (
            await session.execute(
                text(
                    "INSERT INTO credit_cards (user_id, name, currency, closing_day, due_day) VALUES (:u, 'Query card', 'ARS', 20, 10) RETURNING id"
                ),
                {"u": seeded["users"][0]},
            )
        ).scalar_one()
        for day, amount, currency in ((date(2026, 6, 3), 1500, "ARS"), (date(2026, 6, 4), 2500, "ARS"), (date(2026, 6, 5), 70, "USD")):
            await session.execute(
                text(
                    "INSERT INTO shared_expenses (group_id, date, amount, currency, split_method, payment_method, credit_card_id)"
                    " VALUES (:g, :d, :a, :c, 'equal', 'credit_card', :card)"
                ),
                {"g": seeded["group"], "d": day, "a": amount, "c": currency, "card": card},
            )
        await session.flush()

        grouped = await shared_expense_repository.sum_by_credit_card_ids_grouped(session, [card])

        # Nested by card then currency — the shape the private sum returns, because the two are merged
        # bucket by bucket. A flat or overwritten mapping loses whichever bucket came second.
        assert grouped == {card: {"ARS": Decimal("4000"), "USD": Decimal("70")}}


class TestTheSettlementLegSums:
    @pytest.mark.asyncio
    async def test_a_same_currency_leg_moves_the_bucket_amount(self, session, seeded):
        await session.execute(
            text(
                "INSERT INTO group_settlements (group_id, from_member_id, to_member_id, date, amount, currency, from_account_id)"
                " VALUES (:g, :f, :t, '2026-06-20', 2500, 'ARS', :a)"
            ),
            {"g": seeded["group"], "f": seeded["seats"][0], "t": seeded["seats"][1], "a": seeded["account"]},
        )
        await session.flush()
        assert await group_settlement_repository.sum_out_by_account_ids(session, [seeded["account"]]) == {seeded["account"]: Decimal("2500.00")}

    @pytest.mark.asyncio
    async def test_a_cross_currency_leg_moves_the_accounts_own_figure(self, session, seeded):
        # The whole reason there are two amounts. Reading `amount` here would take 2,500 PESOS out of
        # a dollar account.
        await session.execute(
            text(
                "INSERT INTO group_settlements"
                " (group_id, from_member_id, to_member_id, date, amount, currency, from_account_id, from_amount)"
                " VALUES (:g, :f, :t, '2026-06-20', 2500, 'ARS', :a, 2)"
            ),
            {"g": seeded["group"], "f": seeded["seats"][0], "t": seeded["seats"][1], "a": seeded["usd_account"]},
        )
        await session.flush()
        assert await group_settlement_repository.sum_out_by_account_ids(session, [seeded["usd_account"]]) == {seeded["usd_account"]: Decimal("2.00")}

    @pytest.mark.asyncio
    async def test_each_leg_reads_its_own_column(self, session, seeded):
        # Both legs of ONE cross-currency settlement, so a query reading the wrong leg's amount shows
        # up as the two accounts moving by each other's figure.
        await session.execute(
            text(
                "INSERT INTO group_settlements"
                " (group_id, from_member_id, to_member_id, date, amount, currency, from_account_id, from_amount, to_account_id)"
                " VALUES (:g, :f, :t, '2026-06-20', 2500, 'ARS', :fa, 2, :ta)"
            ),
            {
                "g": seeded["group"],
                "f": seeded["seats"][0],
                "t": seeded["seats"][1],
                "fa": seeded["usd_account"],
                "ta": seeded["account"],
            },
        )
        await session.flush()
        out = await group_settlement_repository.sum_out_by_account_ids(session, [seeded["usd_account"], seeded["account"]])
        into = await group_settlement_repository.sum_in_by_account_ids(session, [seeded["usd_account"], seeded["account"]])
        assert out == {seeded["usd_account"]: Decimal("2.00")}
        # The receiving side had no conversion of its own, so it moves the bucket amount.
        assert into == {seeded["account"]: Decimal("2500.00")}

    @pytest.mark.asyncio
    async def test_a_written_off_balance_moves_no_account(self, session, seeded):
        await session.execute(
            text(
                "INSERT INTO group_settlements (group_id, from_member_id, to_member_id, date, amount, currency, status)"
                " VALUES (:g, :f, :t, '2026-06-20', 2500, 'ARS', 'written_off')"
            ),
            {"g": seeded["group"], "f": seeded["seats"][0], "t": seeded["seats"][1]},
        )
        await session.flush()
        assert await group_settlement_repository.sum_out_by_account_ids(session, [seeded["account"]]) == {}
        # It still clears the balance, which is the whole point of it.
        assert len(await group_settlement_repository.list_movements_by_groups(session, [seeded["group"]])) == 1
