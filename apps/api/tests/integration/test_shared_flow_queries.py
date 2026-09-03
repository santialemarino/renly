import os
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# The queries whose whole correctness lives in the SQL, driven against a real Postgres.
#
#   * the /expenses and /income UNIONS — a mocked session cannot tell a union that returns the caller's
#     share from one that returns the whole row, or one whose page order is not a total order;
#   * the balance AGGREGATIONS — two columns summed per member per currency, per flow, which a mock
#     returns whatever it was told for. And the property no unit test can reach at all: the two flows
#     land in the SAME bucket and have to net there, with each read in its own direction;
#   * the settlement LEG sums — the `coalesce(<leg>_amount, amount)` that decides whether a
#     cross-currency settlement moves the bucket's figure or the account's;
#   * the shared-income account sums, whose opening_date bound lives entirely in a join;
#   * the DASHBOARD's own reads over the same tables, added when the aggregates learned to see the
#     shared side. Three of them are two-queries-one-fact pairs and belong here for that reason alone:
#     the monthly positions the chart derives a balance-per-month from must equal the live positions
#     the group hub shows at their last month; the finance dashboard's spending and earning totals must
#     equal the lists they summarise; and a group's card charge must reach the monthly card series as
#     well as the current card balance, which it did not before.
#
# Skipped unless LEDGER_TEST_DATABASE_URL points at a database with the schema applied, matching the
# contract the other query suites use.
from app.domain.list_scope import ListScope
from app.domain.shared_flow import apply_settlements, combine_positions, expense_positions, income_positions, minimise_transfers
from app.repositories import expense_repository, group_settlement_repository, income_repository, shared_expense_repository, shared_income_repository
from app.services import group_settlement_service

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

    # The income half. One private entry sharing a date with a shared one, then shared income in both
    # buckets and in both destination shapes.
    for day, amount in ((date(2026, 5, 20), 7000), (date(2026, 7, 1), 1200)):
        await session.execute(
            text("INSERT INTO income_entries (user_id, date, amount, currency, category, notes) VALUES (:u, :d, :a, 'ARS', 'salary', 'own pay')"),
            {"u": users[0], "d": day, "a": amount},
        )

    async def earned(
        day: date, amount: int, currency: str, destination: str, splits: dict[int, tuple[int, int]], notes: str = "rent", account_id=None
    ):
        row = await scalar(
            "INSERT INTO shared_income (group_id, date, amount, currency, category, split_method, destination, paid_to_account_id, notes)"
            " VALUES (:g, :d, :a, :c, 'rental_income', 'equal', :dest, :acc, :n) RETURNING id",
            g=group,
            d=day,
            a=amount,
            c=currency,
            dest=destination,
            acc=account_id,
            n=notes,
        )
        for seat, (entitled, received) in splits.items():
            await session.execute(
                text("INSERT INTO shared_income_splits (shared_income_id, group_id, member_id, amount, received_amount) VALUES (:i, :g, :m, :a, :r)"),
                {"i": row, "g": group, "m": seat, "a": entitled, "r": received},
            )
        return row

    # 90 USD, a second bucket that must never net with the first.
    await earned(date(2026, 6, 12), 90, "USD", "distributed", {seats[0]: (45, 90), seats[1]: (45, 0)}, notes="usd rent")
    # One where seat A collected money they are entitled to none of: an entitlement of zero that must
    # not appear as income, and the mirror of the "not mine" expense above.
    await earned(date(2026, 6, 18), 500, "ARS", "distributed", {seats[0]: (0, 500), seats[1]: (500, 0)}, notes="not my income")

    # A shared row and a PRIVATE one sharing an id AND a date, which is the only shape that can tell
    # the page order's scope tie-break apart from its absence: ids are unique per table and not across
    # them, so this pair is genuinely indistinguishable without the scope. A fixture whose ids happened
    # not to collide left the tie-break untestable, which a mutation sweep found.
    #
    # BOTH ids are stated explicitly, taken from one past the highest live id in either table. Letting
    # either sequence choose does not work: neither is transactional, so a rolled-back run leaves them
    # advanced by different amounts, and copying one table's fresh id into the other eventually names an
    # id that table's own sequence has already handed out — a suite that passes once and then fails on
    # a re-run against the same database, which is how this was found. Done LAST in the seeding so
    # every auto-id row is already in, and the chosen id is therefore free in both tables.
    colliding_id = await scalar(
        "SELECT GREATEST(COALESCE((SELECT max(id) FROM shared_income), 0), COALESCE((SELECT max(id) FROM income_entries), 0)) + 1"
    )
    # 6,000 ARS collected by seat B into their own hands and split three ways: B owes the other two.
    # Dated the same day as the private entry below, so a filter that reached one branch only would show it.
    await session.execute(
        text(
            "INSERT INTO shared_income (id, group_id, date, amount, currency, category, split_method, destination, notes)"
            " VALUES (:i, :g, '2026-05-20', 6000, 'ARS', 'rental_income', 'equal', 'distributed', 'rent')"
        ),
        {"i": colliding_id, "g": group},
    )
    for seat, (entitled, received) in {seats[0]: (2000, 0), seats[1]: (2000, 6000), seats[2]: (2000, 0)}.items():
        await session.execute(
            text("INSERT INTO shared_income_splits (shared_income_id, group_id, member_id, amount, received_amount) VALUES (:i, :g, :m, :a, :r)"),
            {"i": colliding_id, "g": group, "m": seat, "a": entitled, "r": received},
        )
    await session.execute(
        text(
            "INSERT INTO income_entries (id, user_id, date, amount, currency, category, notes)"
            " VALUES (:i, :u, '2026-05-20', 111, 'ARS', 'salary', 'collides')"
        ),
        {"i": colliding_id, "u": users[0]},
    )
    # Both sequences pushed past the id just taken by hand, because the TESTS insert further rows of
    # their own: a sequence left behind an explicit id hands that same id out again on the next auto
    # insert. setval does not roll back, which is what makes it the right tool here — the explicit row
    # disappears with the transaction, the reservation does not.
    for table in ("shared_income", "income_entries"):
        await session.execute(
            text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), GREATEST(:i, (SELECT last_value FROM {table}_id_seq)))"),
            {"i": colliding_id},
        )
    await session.flush()
    # The collision is a PROPERTY of this fixture, asserted here rather than trusted: without it the
    # paging test still passes and simply stops testing the tie-break it exists for.
    assert (
        await scalar("SELECT count(*) FROM income_entries WHERE id = :i", i=colliding_id) == 1
        and await scalar("SELECT count(*) FROM shared_income WHERE id = :i", i=colliding_id) == 1
    )
    return {
        "users": users,
        "group": group,
        "seats": seats,
        "account": account,
        "usd_account": usd_account,
        "colliding_id": colliding_id,
    }


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
    async def test_sorting_by_amount_orders_within_each_scope(self, session, seeded):
        # X2 changed what a sort MEANS on this list, deliberately and visibly: the rows are grouped by
        # scope, so the caller's sort applies inside each section rather than across the whole page.
        # A globally sorted page could not carry section headers at all — the two scopes would
        # interleave and the same header would be drawn several times down one page.
        #
        # Asserted per group rather than over the whole list, and the seed makes the distinction real:
        # it holds a private row whose amount falls between two shared ones, so a page that were still
        # globally sorted would fail the grouping assertion and a page sorted only by group would fail
        # the within-section one.
        rows, _ = await expense_repository.list_by_user_filtered(
            session, seeded["users"][0], [seeded["seats"][0]], sort_by="amount", sort_order="desc", page_size=50
        )
        groups = [row.group_id for row in rows]
        assert groups == sorted(groups, key=lambda g: (g is not None, g or 0))
        by_group: dict = {}
        for row in rows:
            by_group.setdefault(row.group_id, []).append(row.amount)
        assert len(by_group) > 1
        for group_id, amounts in by_group.items():
            assert amounts == sorted(amounts, reverse=True), group_id

    @pytest.mark.asyncio
    async def test_asking_for_one_scope_gives_back_a_flat_globally_sorted_list(self, session, seeded):
        # Which is the other half of the same rule: the pill FILTERS, so narrowing to one scope
        # collapses the grouping to a single section and the sort is global again.
        rows, _ = await expense_repository.list_by_user_filtered(
            session,
            seeded["users"][0],
            [seeded["seats"][0]],
            scope=ListScope.shared,
            sort_by="amount",
            sort_order="desc",
            page_size=50,
        )
        assert {row.scope for row in rows} == {"shared"}
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


# A monthly aggregate summed back to one figure per currency. Written once because the per-month rows
# are what the aggregate returns and the totals are what the dashboard shows — collapsing them with a
# dict comprehension keyed on currency silently keeps only the LAST month, which is how the first draft
# of two of these tests came to assert the wrong figure.
def _by_currency(rows) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for _year, _month, currency, total in rows:
        totals[currency] = totals.get(currency, Decimal(0)) + total
    return totals


class TestTheMonthlyPositions:
    # The dashboard's net-worth chart derives a balance per month from its OWN aggregates, while the
    # group hub derives today's from the live ones. Two queries, one fact — the shape a mocked session
    # is structurally unable to notice going wrong, because it returns whatever it was told for both.
    #
    # The parity below is the load-bearing one: the last month of the monthly series must equal the
    # live positions exactly, member by member, in every bucket.
    @pytest.mark.asyncio
    async def test_the_last_month_equals_the_LIVE_positions(self, session, seeded):
        await session.execute(
            text(
                "INSERT INTO group_settlements (group_id, from_member_id, to_member_id, date, amount, currency)"
                " VALUES (:g, :f, :t, '2026-07-02', 1000, 'ARS')"
            ),
            {"g": seeded["group"], "f": seeded["seats"][1], "t": seeded["seats"][0]},
        )
        await session.flush()

        # The INTERNAL derivation on purpose: it is the one get_balances runs for the group hub, and
        # the dashboard now reads the monthly series' last entry instead of issuing it a second time.
        # This equality is what makes that substitution safe.
        live = await group_settlement_service._positions_by_group(session, [seeded["group"]])
        series = await group_settlement_service.get_positions_by_month(session, [seeded["group"]])

        assert series, "the fixture has flow rows, so the series cannot be empty"
        assert series[-1][1] == live
        # A positive control: a fixture whose positions were all zero would satisfy the equality above
        # while testing nothing.
        assert any(amount != Decimal(0) for by_currency in live.values() for net in by_currency.values() for amount in net.values())

    @pytest.mark.asyncio
    async def test_it_is_cumulative_rather_than_per_month(self, session, seeded):
        # Every month carries every row on or before it. Asserted by comparing the FIRST month against
        # the live positions restricted to rows up to that month — a per-month aggregate would report
        # only that month's movement and the two would diverge from the second month on.
        series = await group_settlement_service.get_positions_by_month(session, [seeded["group"]])
        months = [month for month, _ in series]
        assert months == sorted(months)
        # The fixture spans May to July, so there is more than one month to be cumulative across.
        assert len(months) > 1
        totals = [
            sum(abs(amount) for by_currency in positions.values() for net in by_currency.values() for amount in net.values())
            for _month, positions in series
        ]
        assert totals[-1] > totals[0]

    @pytest.mark.asyncio
    async def test_each_month_is_bucketed_by_its_own_rows_date(self, session, seeded):
        rows = await shared_expense_repository.list_positions_by_groups_monthly(session, [seeded["group"]])
        # Every shared expense in the fixture is dated June.
        assert {(year, month) for _g, year, month, _c, _m, _a, _p in rows} == {(2026, 6)}
        income = await shared_income_repository.list_positions_by_groups_monthly(session, [seeded["group"]])
        assert {(year, month) for _g, year, month, _c, _m, _a, _r in income} == {(2026, 5), (2026, 6)}

    @pytest.mark.asyncio
    async def test_the_monthly_totals_sum_to_the_live_ones_per_bucket(self, session, seeded):
        # The columns, not only the shape: summing the monthly aggregate over every month has to give
        # the live aggregate's two figures back. A crossed pair of columns type-checks and still nets
        # to zero, so it is the sums that have to be compared rather than the balances.
        live = {(c, m): (a, p) for _g, c, m, a, p in await shared_expense_repository.list_positions_by_groups(session, [seeded["group"]])}
        monthly: dict[tuple[str, int], tuple[Decimal, Decimal]] = {}
        for _g, _y, _mo, currency, member_id, amount, paid in await shared_expense_repository.list_positions_by_groups_monthly(
            session, [seeded["group"]]
        ):
            running = monthly.get((currency, member_id), (Decimal(0), Decimal(0)))
            monthly[(currency, member_id)] = (running[0] + amount, running[1] + paid)
        assert monthly == live


class TestTheDashboardsSpendingAndEarningUnions:
    # The finance dashboard sums the caller's spending and earnings; the list pages show them row by
    # row. Both now read the same two tables, and the property that matters is that the aggregate
    # equals the list — which is exactly what a mocked session cannot check, because the aggregate and
    # the list are different SQL over the same rows.
    @pytest.mark.asyncio
    async def test_the_monthly_expense_total_equals_the_list_it_summarises(self, session, seeded):
        user, seat = seeded["users"][0], seeded["seats"][0]
        rows, _ = await expense_repository.list_by_user_filtered(session, user, [seat], page_size=200)
        listed: dict[str, Decimal] = {}
        for row in rows:
            listed[row.currency] = listed.get(row.currency, Decimal(0)) + row.amount

        assert _by_currency(await expense_repository.sum_by_user_monthly(session, user, [seat])) == listed
        # The positive control: the shared branch really is in there, so the equality is not two
        # private-only reads agreeing with each other.
        assert any(row.scope == "shared" for row in rows)

    @pytest.mark.asyncio
    async def test_the_monthly_totals_are_bucketed_by_MONTH(self, session, seeded):
        # Every other assertion here sums across months and is therefore blind to the bucketing itself
        # — a mutation swapping the month extraction for a second year extraction left them all green.
        # The fixture spans May (private only), June (private + both shared buckets) and July (income),
        # so a wrong bucket collapses three months into one.
        user, seat = seeded["users"][0], seeded["seats"][0]
        expense = {(year, month, currency) for year, month, currency, _t in await expense_repository.sum_by_user_monthly(session, user, [seat])}
        assert expense == {(2026, 5, "ARS"), (2026, 6, "ARS"), (2026, 6, "USD")}
        income = {(year, month, currency) for year, month, currency, _t in await income_repository.sum_by_user_monthly(session, user, [seat])}
        assert income == {(2026, 5, "ARS"), (2026, 6, "USD"), (2026, 7, "ARS")}

    @pytest.mark.asyncio
    async def test_the_category_breakdown_equals_the_same_list(self, session, seeded):
        user, seat = seeded["users"][0], seeded["seats"][0]
        rows, _ = await expense_repository.list_by_user_filtered(session, user, [seat], page_size=200)
        listed: dict[tuple[str, str], Decimal] = {}
        for row in rows:
            key = ("uncategorized" if row.category is None else str(row.category), row.currency)
            listed[key] = listed.get(key, Decimal(0)) + row.amount
        summed = {
            (category, currency): total
            for category, currency, total in await expense_repository.sum_by_user_grouped_by_category(session, user, [seat])
        }
        assert summed == listed
        # Both the private category and the shared one are represented, so a branch that vanished
        # would change the keyset rather than only a figure.
        assert {"food", "dining"} <= {category for category, _currency in summed}

    @pytest.mark.asyncio
    async def test_a_zero_share_is_excluded_from_the_totals_just_as_it_is_from_the_list(self, session, seeded):
        # A payer who took no part spent nothing. The fixture's "not mine" expense is 400 ARS fronted
        # by seat A with a zero share, so it must not reach the ARS total.
        user, seat = seeded["users"][0], seeded["seats"][0]
        summed = _by_currency(await expense_repository.sum_by_user_monthly(session, user, [seat]))
        # 1,000 + 2,000 private, plus a 3,000 share of the dinner. The 400 is absent.
        assert summed["ARS"] == Decimal("6000.00")

    @pytest.mark.asyncio
    async def test_a_user_in_no_group_gets_exactly_their_private_totals(self, session, seeded):
        user = seeded["users"][0]
        summed = _by_currency(await expense_repository.sum_by_user_monthly(session, user, []))
        assert summed == {"ARS": Decimal("3000.00")}

    @pytest.mark.asyncio
    async def test_the_income_total_equals_the_income_list(self, session, seeded):
        user, seat = seeded["users"][0], seeded["seats"][0]
        rows, _ = await income_repository.list_by_user_filtered(session, user, [seat], page_size=200)
        listed: dict[str, Decimal] = {}
        for row in rows:
            listed[row.currency] = listed.get(row.currency, Decimal(0)) + row.amount
        assert _by_currency(await income_repository.sum_by_user_monthly(session, user, [seat])) == listed
        assert any(row.scope == "shared" for row in rows)

    @pytest.mark.asyncio
    async def test_the_income_total_counts_the_ENTITLEMENT_not_what_arrived(self, session, seeded):
        # `amount` on a split is what the member is entitled to; `received_amount` is what reached
        # them, and the gap between the two is a BALANCE rather than earnings. Seat A is entitled to
        # 45 USD of the rent and received 90 of it, so their income is 45.
        user, seat = seeded["users"][0], seeded["seats"][0]
        summed = _by_currency(await income_repository.sum_by_user_monthly(session, user, [seat]))
        assert summed["USD"] == Decimal("45.00")

    @pytest.mark.asyncio
    async def test_a_zero_ENTITLEMENT_does_not_move_the_first_income_date(self, session, seeded):
        # Where the `amount > 0` filter is actually observable. In a SUM a zero contributes zero either
        # way, so no total can tell the predicate from its absence — but a MIN(date) can: a row somebody
        # collected and is entitled to none of would otherwise back-date their income history and change
        # what the liquidity card thinks it has to work with.
        user, seat = seeded["users"][0], seeded["seats"][0]
        row = (
            await session.execute(
                text(
                    "INSERT INTO shared_income (group_id, date, amount, currency, category, split_method, destination)"
                    " VALUES (:g, '2024-01-05', 900, 'ARS', 'rental_income', 'equal', 'distributed') RETURNING id"
                ),
                {"g": seeded["group"]},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO shared_income_splits (shared_income_id, group_id, member_id, amount, received_amount) VALUES (:i, :g, :m, 0, 900)"),
            {"i": row, "g": seeded["group"], "m": seat},
        )
        await session.flush()
        assert await income_repository.get_first_income_date(session, user, [seat]) == date(2026, 5, 20)

    @pytest.mark.asyncio
    async def test_the_first_income_date_sees_the_shared_side(self, session, seeded):
        # The liquidity card's history gate. The caller's own earliest private entry is 2026-05-20 and
        # so is a shared one, so the discriminating check is that adding an EARLIER shared row moves it.
        user, seat = seeded["users"][0], seeded["seats"][0]
        before = await income_repository.get_first_income_date(session, user, [seat])
        row = (
            await session.execute(
                text(
                    "INSERT INTO shared_income (group_id, date, amount, currency, category, split_method, destination)"
                    " VALUES (:g, '2026-02-02', 100, 'ARS', 'rental_income', 'equal', 'distributed') RETURNING id"
                ),
                {"g": seeded["group"]},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO shared_income_splits (shared_income_id, group_id, member_id, amount, received_amount) VALUES (:i, :g, :m, 100, 0)"),
            {"i": row, "g": seeded["group"], "m": seat},
        )
        await session.flush()
        assert before == date(2026, 5, 20)
        assert await income_repository.get_first_income_date(session, user, [seat]) == date(2026, 2, 2)
        # And a caller in no group still reads only their own history.
        assert await income_repository.get_first_income_date(session, user, []) == date(2026, 5, 20)


class TestTheMonthlyCardCharges:
    # get_card_balances merges a group's charges into the CURRENT card balance; the evolution chart's
    # monthly series has to merge the same rows or the headline and the chart describe different debts.
    @pytest.mark.asyncio
    async def test_a_groups_charge_appears_in_the_monthly_series_too(self, session, seeded):
        card = (
            await session.execute(
                text(
                    "INSERT INTO credit_cards (user_id, name, closing_day, due_day, currency) VALUES (:u, 'Monthly card', 20, 5, 'ARS') RETURNING id"
                ),
                {"u": seeded["users"][0]},
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO shared_expenses (group_id, date, amount, currency, category, split_method, payment_method, credit_card_id)"
                " VALUES (:g, '2026-06-09', 2500, 'ARS', 'dining', 'equal', 'credit_card', :c)"
            ),
            {"g": seeded["group"], "c": card},
        )
        await session.flush()

        monthly = await shared_expense_repository.sum_by_credit_card_ids_monthly(session, [card])
        assert monthly == [(card, 2026, 6, "ARS", 2500.0)]
        # And it agrees with the grouped read the current balance uses, which is the figure the chart
        # has to end at.
        grouped = await shared_expense_repository.sum_by_credit_card_ids_grouped(session, [card])
        assert Decimal(str(grouped[card]["ARS"])) == Decimal(str(sum(total for _c, _y, _m, _cur, total in monthly)))


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


class TestTheIncomeUnion:
    @pytest.mark.asyncio
    async def test_it_returns_the_callers_share_not_the_whole_income(self, session, seeded):
        rows, total = await income_repository.list_by_user_filtered(session, seeded["users"][0], [seeded["seats"][0]], page_size=50)
        shared = sorted((row.currency, row.amount, row.full_amount) for row in rows if row.scope == "shared")
        # The caller's SHARE beside the whole row, in both buckets. A union reading `amount` from the
        # parent would report 6,000 and 90 here — what the group received rather than what this person
        # is entitled to, which is the same mistake D2 forbids on the way out.
        assert shared == [("ARS", Decimal("2000.00"), Decimal("6000.00")), ("USD", Decimal("45.00"), Decimal("90.00"))]
        assert total == len(rows) == 5

    @pytest.mark.asyncio
    async def test_a_zero_entitlement_never_appears(self, session, seeded):
        # A collector entitled to nothing holds a position in the row but earned nothing from it, so it
        # is not income. The mirror of the zero-share expense.
        rows, _ = await income_repository.list_by_user_filtered(session, seeded["users"][0], [seeded["seats"][0]], page_size=50)
        assert all(row.notes != "not my income" for row in rows)

    @pytest.mark.asyncio
    async def test_a_user_in_no_group_sees_only_their_own(self, session, seeded):
        rows, total = await income_repository.list_by_user_filtered(session, seeded["users"][0], [], page_size=50)
        assert {row.scope for row in rows} == {"private"}
        assert total == 3

    @pytest.mark.asyncio
    async def test_paging_never_repeats_or_drops_a_row(self, session, seeded):
        """The reason the tie-break carries the scope: ids are unique per TABLE and this list spans two.

        The fixture holds a private row and a shared row sharing a date AND an id, so without the
        scope in the order the two have no total order at all — Postgres may then hand the same one
        back on two pages and never show the other. With ids that happened not to collide this test
        passed either way, which is what a mutation sweep found.
        """
        seen: list[tuple[str, int]] = []
        page = 1
        while True:
            rows, total = await income_repository.list_by_user_filtered(session, seeded["users"][0], [seeded["seats"][0]], page=page, page_size=1)
            if not rows:
                break
            seen.extend((row.scope, row.id) for row in rows)
            if len(seen) >= total:
                break
            page += 1
        assert len(set(seen)) == len(seen) == 5
        # And the colliding pair is BOTH there, which is the property the scope buys.
        assert {("private", seeded["colliding_id"]), ("shared", seeded["colliding_id"])} <= set(seen)

    @pytest.mark.asyncio
    async def test_a_filter_narrows_both_branches_together(self, session, seeded):
        rows, _ = await income_repository.list_by_user_filtered(
            session, seeded["users"][0], [seeded["seats"][0]], date_from=date(2026, 5, 20), date_to=date(2026, 5, 20), page_size=50
        )
        # Private and shared rows share that date, so a filter that reached only one branch would come
        # back short.
        assert sorted(row.scope for row in rows) == ["private", "private", "shared"]

    @pytest.mark.asyncio
    async def test_sorting_by_amount_orders_within_each_scope(self, session, seeded):
        # X2 changed what a sort MEANS on this list, deliberately and visibly: the rows are grouped by
        # scope, so the caller's sort applies inside each section rather than across the whole page.
        # A globally sorted page could not carry section headers at all — the two scopes would
        # interleave and the same header would be drawn several times down one page.
        #
        # Asserted per group rather than over the whole list, and the seed makes the distinction real:
        # it holds a private row whose amount falls between two shared ones, so a page that were still
        # globally sorted would fail the grouping assertion and a page sorted only by group would fail
        # the within-section one.
        rows, _ = await income_repository.list_by_user_filtered(
            session, seeded["users"][0], [seeded["seats"][0]], sort_by="amount", sort_order="desc", page_size=50
        )
        groups = [row.group_id for row in rows]
        assert groups == sorted(groups, key=lambda g: (g is not None, g or 0))
        by_group: dict = {}
        for row in rows:
            by_group.setdefault(row.group_id, []).append(row.amount)
        assert len(by_group) > 1
        for group_id, amounts in by_group.items():
            assert amounts == sorted(amounts, reverse=True), group_id

    @pytest.mark.asyncio
    async def test_asking_for_one_scope_gives_back_a_flat_globally_sorted_list(self, session, seeded):
        # Which is the other half of the same rule: the pill FILTERS, so narrowing to one scope
        # collapses the grouping to a single section and the sort is global again.
        rows, _ = await income_repository.list_by_user_filtered(
            session,
            seeded["users"][0],
            [seeded["seats"][0]],
            scope=ListScope.shared,
            sort_by="amount",
            sort_order="desc",
            page_size=50,
        )
        assert {row.scope for row in rows} == {"shared"}
        assert [row.amount for row in rows] == sorted((row.amount for row in rows), reverse=True)

    @pytest.mark.asyncio
    async def test_a_shared_row_carries_its_group_and_no_account(self, session, seeded):
        # `account_id` is nulled on the shared branch on purpose: it identifies where the money LANDED,
        # which is frequently another member's account.
        rows, _ = await income_repository.list_by_user_filtered(session, seeded["users"][0], [seeded["seats"][0]], page_size=50)
        shared = [row for row in rows if row.scope == "shared"]
        assert {row.group_id for row in shared} == {seeded["group"]}
        assert {row.account_id for row in shared} == {None}
        assert {row.source for row in shared} == {"shared"}


class TestTheIncomeBalanceAggregation:
    @pytest.mark.asyncio
    async def test_positions_come_back_per_currency_per_member(self, session, seeded):
        rows = [row[1:] for row in await shared_income_repository.list_positions_by_groups(session, [seeded["group"]])]
        by_key = {(currency, member_id): (entitled, received) for currency, member_id, entitled, received in rows}
        # Seat A: entitled to 2,000 of the ARS rent and holding 500 they are entitled to none of.
        assert by_key[("ARS", seeded["seats"][0])] == (Decimal("2000.00"), Decimal("500.00"))
        assert by_key[("USD", seeded["seats"][0])] == (Decimal("45.00"), Decimal("90.00"))

    @pytest.mark.asyncio
    async def test_the_two_flows_net_in_ONE_bucket(self, session, seeded):
        # The property no unit test can reach: both flows land in the same per-currency bucket and have
        # to net there, each read in its own direction. Seat A fronted an expense (owed) and collected
        # income they had no share of (owing), so the two really do offset — and if either aggregate
        # were read backwards, each flow would still sum to zero on its own while this figure was wrong.
        expenses = [row[1:] for row in await shared_expense_repository.list_positions_by_groups(session, [seeded["group"]])]
        earned = [row[1:] for row in await shared_income_repository.list_positions_by_groups(session, [seeded["group"]])]
        movements = [row[1:] for row in await group_settlement_repository.list_movements_by_groups(session, [seeded["group"]])]
        for currency in {row[0] for row in expenses} | {row[0] for row in earned}:
            flows = combine_positions(
                expense_positions([(member_id, consumed, fronted) for c, member_id, consumed, fronted in expenses if c == currency]),
                income_positions([(member_id, entitled, received) for c, member_id, entitled, received in earned if c == currency]),
            )
            net = apply_settlements(flows, [(f, t, a) for c, f, t, a in movements if c == currency])
            assert sum(net.values(), Decimal(0)) == Decimal(0), currency
            # And the plan derived from it clears the bucket exactly, expenses and income together.
            moved = [(t.from_member_id, t.to_member_id, t.amount) for t in minimise_transfers(net)]
            assert apply_settlements(net, moved) == {}

    @pytest.mark.asyncio
    async def test_the_flows_do_not_cancel_by_accident(self, session, seeded):
        # The positive control for the test above: an all-zero bucket satisfies a zero-sum assertion
        # trivially, so assert the members actually hold positions.
        expenses = [row[1:] for row in await shared_expense_repository.list_positions_by_groups(session, [seeded["group"]])]
        earned = [row[1:] for row in await shared_income_repository.list_positions_by_groups(session, [seeded["group"]])]
        ars = combine_positions(
            expense_positions([(member_id, consumed, fronted) for c, member_id, consumed, fronted in expenses if c == "ARS"]),
            income_positions([(member_id, entitled, received) for c, member_id, entitled, received in earned if c == "ARS"]),
        )
        # Seat A: +9,400 fronted −3,000 consumed on the expenses, +2,000 entitled −500 collected on the
        # income = 7,900. Read either aggregate backwards and this is a different number.
        assert ars[seeded["seats"][0]] == Decimal("7900.00")


class TestTheSharedIncomeAccountSums:
    # The account leg's bound lives entirely in a join to accounts, which a mocked session cannot
    # exercise at all: opening_balance IS the balance at the opening date, so a row dated earlier is
    # already inside it and summing it again double-counts.
    @pytest.mark.asyncio
    async def test_income_into_an_account_sums_the_whole_amount(self, session, seeded):
        await session.execute(
            text(
                "INSERT INTO shared_income (group_id, date, amount, currency, split_method, destination, paid_to_account_id)"
                " VALUES (:g, '2026-06-05', 4000, 'ARS', 'equal', 'distributed', :a)"
            ),
            {"g": seeded["group"], "a": seeded["account"]},
        )
        await session.flush()
        # The WHOLE amount, not anyone's share: the money really arrived in that account.
        assert await shared_income_repository.sum_by_account_ids(session, [seeded["account"]]) == {seeded["account"]: Decimal("4000.00")}

    @pytest.mark.asyncio
    async def test_a_row_dated_before_the_account_opened_is_excluded(self, session, seeded):
        await session.execute(
            text(
                "INSERT INTO shared_income (group_id, date, amount, currency, split_method, destination, paid_to_account_id)"
                " VALUES (:g, '2025-12-31', 4000, 'ARS', 'equal', 'distributed', :a)"
            ),
            {"g": seeded["group"], "a": seeded["account"]},
        )
        await session.flush()
        assert await shared_income_repository.sum_by_account_ids(session, [seeded["account"]]) == {}

    @pytest.mark.asyncio
    async def test_the_as_of_bound_excludes_later_rows(self, session, seeded):
        for day in (date(2026, 6, 5), date(2026, 8, 5)):
            await session.execute(
                text(
                    "INSERT INTO shared_income (group_id, date, amount, currency, split_method, destination, paid_to_account_id)"
                    " VALUES (:g, :d, 1000, 'ARS', 'equal', 'distributed', :a)"
                ),
                {"g": seeded["group"], "d": day, "a": seeded["account"]},
            )
        await session.flush()
        totals = await shared_income_repository.sum_by_account_ids(session, [seeded["account"]], as_of_date=date(2026, 7, 1))
        assert totals == {seeded["account"]: Decimal("1000.00")}

    @pytest.mark.asyncio
    async def test_the_dated_variant_groups_by_day(self, session, seeded):
        for day in (date(2026, 6, 5), date(2026, 6, 5), date(2026, 8, 5)):
            await session.execute(
                text(
                    "INSERT INTO shared_income (group_id, date, amount, currency, split_method, destination, paid_to_account_id)"
                    " VALUES (:g, :d, 1000, 'ARS', 'equal', 'distributed', :a)"
                ),
                {"g": seeded["group"], "d": day, "a": seeded["account"]},
            )
        await session.flush()
        # A PRE-OPENING row as well, because the dated variant carries the same bound in its own join
        # and a sweep found it uncovered: the point-in-time test above proved only the other query's.
        await session.execute(
            text(
                "INSERT INTO shared_income (group_id, date, amount, currency, split_method, destination, paid_to_account_id)"
                " VALUES (:g, '2025-11-30', 9999, 'ARS', 'equal', 'distributed', :a)"
            ),
            {"g": seeded["group"], "a": seeded["account"]},
        )
        await session.flush()
        rows = await shared_income_repository.sum_by_account_ids_dated(session, [seeded["account"]], until=date(2026, 7, 1))
        # Two rows on one day come back as ONE summed row, which is what the series accumulator needs:
        # it adds each (account, date) delta once. The pre-opening row appears in neither.
        assert rows == [(seeded["account"], date(2026, 6, 5), Decimal("2000.00"))]

    @pytest.mark.asyncio
    async def test_the_currency_lock_sees_an_account_income_has_landed_in(self, session, seeded):
        # Unbounded by opening_date, unlike the sums: a pre-opening row contributes nothing to the
        # balance but is still denominated in the account's currency.
        await session.execute(
            text(
                "INSERT INTO shared_income (group_id, date, amount, currency, split_method, destination, paid_to_account_id)"
                " VALUES (:g, '2025-12-31', 4000, 'ARS', 'equal', 'distributed', :a)"
            ),
            {"g": seeded["group"], "a": seeded["account"]},
        )
        await session.flush()
        assert await shared_income_repository.linked_account_ids(session, [seeded["account"], seeded["usd_account"]]) == {seeded["account"]}

    @pytest.mark.asyncio
    async def test_deleting_the_account_a_JOINT_row_names_leaves_the_row_standing(self, session, seeded):
        # The reason `destination = 'joint'` carries no CHECK requiring an account. The FK is
        # ON DELETE SET NULL, so a constraint pairing the two columns turns this delete into a refusal
        # — and the refusal is not even a legible one, since main.py maps every IntegrityError to a
        # bare 409. What must survive instead is the row and its splits: the money did stay together,
        # and who was credited what is on the split rows, which the deletion does not touch.
        income = (
            await session.execute(
                text(
                    "INSERT INTO shared_income (group_id, date, amount, currency, split_method, destination, paid_to_account_id)"
                    " VALUES (:g, '2026-06-10', 5000, 'ARS', 'equal', 'joint', :a) RETURNING id"
                ),
                {"g": seeded["group"], "a": seeded["account"]},
            )
        ).scalar_one()
        await session.execute(
            text("INSERT INTO shared_income_splits (shared_income_id, group_id, member_id, amount, received_amount) VALUES (:i, :g, :m, 2500, 2500)"),
            {"i": income, "g": seeded["group"], "m": seeded["seats"][0]},
        )
        await session.execute(text("DELETE FROM accounts WHERE id = :a"), {"a": seeded["account"]})
        await session.flush()

        row = (await session.execute(text("SELECT destination, paid_to_account_id FROM shared_income WHERE id = :i"), {"i": income})).one()
        assert row == ("joint", None)
        splits = (
            await session.execute(text("SELECT amount, received_amount FROM shared_income_splits WHERE shared_income_id = :i"), {"i": income})
        ).all()
        assert splits == [(Decimal("2500.00"), Decimal("2500.00"))]
