import os
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# The one arithmetic claim the whole fourth guided flow rests on, proved against a real database
# rather than argued: contributing a holding moves NOBODY's value.
#
# It cannot be a unit test, and not because of a stub or two. The claim spans the ledger replay, the
# NAV sum over what the pot holds, the per-account balance union, the unit division and the
# remainder-carrying share split — five things, four of which read SQL. A mocked session answers each
# of them with whatever it was handed, so a unit test of this asserts its own fixture.
#
# The fixture is chosen so every figure is exact and the failure mode is visible as a TRANSFER:
#
#   pot holds one investment worth 110, divided 60/40 at a baseline of 100  ->  price 1.10
#   the contributor hands over a private investment worth 55                ->  50 units issued
#   afterwards: NAV 165 over 150 units                                      ->  price 1.10, unchanged
#
#   contributor  60u -> 110u :  66.00 -> 121.00   (+55.00, exactly what they put in)
#   the other    40u ->  40u :  44.00 ->  44.00   (unchanged, to the cent)
#
# Price the contribution AFTER the move instead — the one ordering mistake available here — and the
# same fixture issues 33.333333 units at 1.65, leaving the contributor on 115.50 and handing the other
# owner 49.50 for doing nothing. A 5.50 transfer, silent, from exactly two statements swapped.
#
# Owner role: this is about what the arithmetic answers, not about who may see it.
from app.models.user import User
from app.services import pot_ownership_service, pot_service

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_EMAIL = "contrib_value@test.local"
_PREFIX = "contrib_"
# Dated well before today so the latest-snapshot-on-or-before-today read finds them whenever this runs.
_VALUED_ON = date(2026, 1, 15)


@pytest_asyncio.fixture
async def seeded():
    engine = create_async_engine(DB_URL)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        await _cleanup(s)
        user = (
            await s.execute(text("INSERT INTO users (name, email, password_hash) VALUES ('contrib', :e, 'h') RETURNING id"), {"e": _EMAIL})
        ).scalar_one()
        group = (
            await s.execute(
                text("INSERT INTO groups (name, kind, created_by) VALUES (:n, 'household', :u) RETURNING id"),
                {"n": f"{_PREFIX}group", "u": user},
            )
        ).scalar_one()
        # The contributor holds the seat; the second seat is a placeholder, which is enough to own
        # units and is what makes "somebody else's value did not move" a real assertion.
        mine = (
            await s.execute(
                text(
                    "INSERT INTO group_members (group_id, user_id, display_name, role, is_active) "
                    "VALUES (:g, :u, 'Santi', 'admin', TRUE) RETURNING id"
                ),
                {"g": group, "u": user},
            )
        ).scalar_one()
        theirs = (
            await s.execute(
                text(
                    "INSERT INTO group_members (group_id, user_id, display_name, role, is_active) "
                    "VALUES (:g, NULL, 'Ana', 'member', TRUE) RETURNING id"
                ),
                {"g": group},
            )
        ).scalar_one()
        pot = (
            await s.execute(text("INSERT INTO pots (group_id, base_currency, is_default) VALUES (:g, 'USD', TRUE) RETURNING id"), {"g": group})
        ).scalar_one()
        await s.execute(
            text("INSERT INTO pot_member_permissions (pot_id, member_id, can_view, can_write) VALUES (:p, :m, TRUE, TRUE)"),
            {"p": pot, "m": mine},
        )

        async def investment(name: str, *, pot_id: int | None, user_id: int | None, value: str, currency: str = "USD") -> int:
            investment_id = (
                await s.execute(
                    text(
                        "INSERT INTO investments (user_id, pot_id, created_by, name, category, base_currency, is_active) "
                        "VALUES (:u, :p, :c, :n, 'stocks', :cur, TRUE) RETURNING id"
                    ),
                    {"u": user_id, "p": pot_id, "c": user, "n": name, "cur": currency},
                )
            ).scalar_one()
            await s.execute(
                text("INSERT INTO investment_snapshots (investment_id, user_id, pot_id, date, value, currency) VALUES (:i, :u, :p, :d, :v, :cur)"),
                {"i": investment_id, "u": user_id, "p": pot_id, "d": _VALUED_ON, "v": value, "cur": currency},
            )
            return investment_id

        held = await investment(f"{_PREFIX}held", pot_id=pot, user_id=None, value="110.00")
        offered = await investment(f"{_PREFIX}offered", pot_id=None, user_id=user, value="55.00")
        # A private cash account, for the OTHER branch of the move. 22.00 at a price of 1.10 is exactly
        # 20 units, so the same fixture stays exact: the contributor goes 60 -> 80 units (66.00 ->
        # 88.00, +22.00) and the other owner stays at 44.00.
        cash = (
            await s.execute(
                text(
                    "INSERT INTO accounts (user_id, created_by, name, type, currency, opening_balance, opening_date, is_active) "
                    "VALUES (:u, :u, :n, 'bank', 'USD', 22.00, :d, TRUE) RETURNING id"
                ),
                {"u": user, "n": f"{_PREFIX}cash", "d": _VALUED_ON},
            )
        ).scalar_one()

        # The baseline: 100 at a nominal 1.00, split 60/40. The pot is worth 110 by the time the
        # contribution happens, which is what makes the price 1.10 rather than a trivial 1.00 — at 1.00
        # the two orderings above would produce the same answer and the test would prove nothing.
        for member_id, units in ((mine, "60"), (theirs, "40")):
            await s.execute(
                text(
                    "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, base_amount, units, unit_price, created_by) "
                    "VALUES (:p, 'opening', :d, :m, :u, :u, 1, :c)"
                ),
                {"p": pot, "d": _VALUED_ON, "m": member_id, "u": units, "c": user},
            )
        await s.commit()
        ids = {
            "user": user,
            "group": group,
            "pot": pot,
            "mine": mine,
            "theirs": theirs,
            "held": held,
            "offered": offered,
            "cash": cash,
            "maker": maker,
        }
    yield ids
    async with maker() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


# Everything this file writes, torn down in FK order: children before parents, and the ledger and the
# permission rows before the pots they hang off, since every pot_id foreign key is RESTRICT.
async def _cleanup(s: AsyncSession) -> None:
    pots = "SELECT id FROM pots WHERE group_id IN (SELECT id FROM groups WHERE name = :n)"
    await s.execute(
        text("DELETE FROM investment_snapshots WHERE investment_id IN (SELECT id FROM investments WHERE name LIKE :p)"), {"p": f"{_PREFIX}%"}
    )
    await s.execute(text("DELETE FROM investments WHERE name LIKE :p"), {"p": f"{_PREFIX}%"})
    await s.execute(text("DELETE FROM accounts WHERE name LIKE :p"), {"p": f"{_PREFIX}%"})
    await s.execute(text("DELETE FROM shared_audit_log WHERE group_id IN (SELECT id FROM groups WHERE name = :n)"), {"n": f"{_PREFIX}group"})
    await s.execute(text(f"DELETE FROM pot_ownership_events WHERE pot_id IN ({pots})"), {"n": f"{_PREFIX}group"})
    await s.execute(text(f"DELETE FROM pot_member_permissions WHERE pot_id IN ({pots})"), {"n": f"{_PREFIX}group"})
    await s.execute(text("DELETE FROM pots WHERE group_id IN (SELECT id FROM groups WHERE name = :n)"), {"n": f"{_PREFIX}group"})
    await s.execute(text("DELETE FROM group_members WHERE group_id IN (SELECT id FROM groups WHERE name = :n)"), {"n": f"{_PREFIX}group"})
    await s.execute(text("DELETE FROM groups WHERE name = :n"), {"n": f"{_PREFIX}group"})
    await s.execute(text("DELETE FROM users WHERE email = :e"), {"e": _EMAIL})


# The fan-out is the one thing here that would open a session of its own, against whatever
# DATABASE_ADMIN_URL happens to name — a developer's real data. Silenced rather than asserted; what
# it announces is pinned in the unit tests.
@pytest.fixture(autouse=True)
def _no_dispatch(monkeypatch):
    monkeypatch.setattr(pot_ownership_service.notification_service, "dispatch", AsyncMock())


async def _shares(maker, pot_id: int, user: User) -> dict[int, Decimal]:
    async with maker() as s:
        response = await pot_service.get_pot(s, pot_id, user)
    return {share.member_id: share.value for share in response.shares}


class TestNobodysValueMoves:
    @pytest.mark.asyncio
    async def test_the_other_owners_share_is_worth_exactly_what_it_was(self, seeded):
        # THE claim. Their units did not change and their value must not either — the pot grew by
        # exactly what the contributor put in, and every cent of that belongs to the contributor.
        user = User(id=seeded["user"], name="Santi", email=_EMAIL, password_hash="h", session_epoch=0)
        before = await _shares(seeded["maker"], seeded["pot"], user)
        assert before[seeded["theirs"]] == Decimal("44.00")

        async with seeded["maker"]() as s:
            await pot_ownership_service.contribute_holding(s, seeded["pot"], user, investment_id=seeded["offered"])

        after = await _shares(seeded["maker"], seeded["pot"], user)
        assert after[seeded["theirs"]] == Decimal("44.00")

    @pytest.mark.asyncio
    async def test_the_contributors_share_grows_by_exactly_what_they_handed_over(self, seeded):
        # The other half, and the reason the first is not enough on its own: a contribution that issued
        # NO units would also leave the other owner on 44.00 while quietly gifting them the growth.
        user = User(id=seeded["user"], name="Santi", email=_EMAIL, password_hash="h", session_epoch=0)
        before = await _shares(seeded["maker"], seeded["pot"], user)
        assert before[seeded["mine"]] == Decimal("66.00")

        async with seeded["maker"]() as s:
            await pot_ownership_service.contribute_holding(s, seeded["pot"], user, investment_id=seeded["offered"])

        after = await _shares(seeded["maker"], seeded["pot"], user)
        assert after[seeded["mine"]] == Decimal("121.00")
        assert after[seeded["mine"]] - before[seeded["mine"]] == Decimal("55.00")

    @pytest.mark.asyncio
    async def test_the_unit_price_is_the_one_from_before_the_move_and_survives_it(self, seeded):
        # What the ordering rule buys, read off the row itself. 1.10 is the price of the pot WITHOUT
        # the contributed holding; pricing after the move would record 1.65 here, and the two share
        # assertions above would both be wrong at once.
        user = User(id=seeded["user"], name="Santi", email=_EMAIL, password_hash="h", session_epoch=0)
        async with seeded["maker"]() as s:
            event = await pot_ownership_service.contribute_holding(s, seeded["pot"], user, investment_id=seeded["offered"])
        assert event.unit_price == Decimal("1.100000")
        assert event.units == Decimal("50.000000")
        assert event.base_amount == Decimal("55.00")

        # And the price is unchanged afterwards, which is the property in its purest form: the pot is
        # worth more and a unit of it is worth the same.
        async with seeded["maker"]() as s:
            pot = await pot_service.get_pot(s, seeded["pot"], user)
        assert pot.unit_price == Decimal("1.100000")
        assert pot.nav == Decimal("165.00")


class TestContributingAnAccount:
    # The other branch of the move, and the one with a money-shaped failure mode a unit test cannot
    # reach: an account carries its own BALANCE into the pot, so the pot's value must rise by that
    # balance exactly ONCE. The two queries that turn an ownership event into account movements
    # (`_FROM_AMOUNT`/`_TO_AMOUNT` in pot_ownership_repository, and `_ownership_branch` in
    # account_movement_repository) both branch on `type == contribution` and both key on the event's
    # account legs — so an asset contribution is invisible to them only because it names NEITHER leg.
    # Populate one "helpfully" and the pot account would be credited base_amount on top of the balance
    # it already has, double-counting the whole contribution. That is what these assertions pin.

    @pytest.mark.asyncio
    async def test_the_pot_gains_the_accounts_balance_exactly_once(self, seeded):
        user = User(id=seeded["user"], name="Santi", email=_EMAIL, password_hash="h", session_epoch=0)
        async with seeded["maker"]() as s:
            await pot_ownership_service.contribute_holding(s, seeded["pot"], user, account_id=seeded["cash"])

        after = await _shares(seeded["maker"], seeded["pot"], user)
        # 110 + 22 = 132 over 120 units, so the price is unchanged at 1.10 and the parts are exact.
        assert after[seeded["mine"]] == Decimal("88.00")
        assert after[seeded["theirs"]] == Decimal("44.00")
        async with seeded["maker"]() as s:
            pot = await pot_service.get_pot(s, seeded["pot"], user)
        assert pot.nav == Decimal("132.00")
        assert pot.unit_price == Decimal("1.100000")

    @pytest.mark.asyncio
    async def test_the_account_moves_and_the_entry_names_no_leg(self, seeded):
        # The account really becomes the pot's — the branch a mutation showed no test reached — and the
        # ledger row names no account on either side, which is what keeps the balance union from
        # counting the same money a second time.
        user = User(id=seeded["user"], name="Santi", email=_EMAIL, password_hash="h", session_epoch=0)
        async with seeded["maker"]() as s:
            event = await pot_ownership_service.contribute_holding(s, seeded["pot"], user, account_id=seeded["cash"])
        assert (event.from_account_id, event.to_account_id) == (None, None)
        assert event.units == Decimal("20.000000")
        async with seeded["maker"]() as s:
            row = (await s.execute(text("SELECT user_id, pot_id FROM accounts WHERE id = :i"), {"i": seeded["cash"]})).one()
        assert (row.user_id, row.pot_id) == (None, seeded["pot"])


class TestTheHoldingReallyMoves:
    @pytest.mark.asyncio
    async def test_the_investment_and_its_snapshots_end_up_in_the_pot(self, seeded):
        # A ledger entry with the holding left behind would issue units against nothing, which is the
        # mirror of the gift and just as silent. The snapshot half matters too: its scope is mirrored
        # for RLS, so a child left naming the old owner is history the pot's members cannot read.
        user = User(id=seeded["user"], name="Santi", email=_EMAIL, password_hash="h", session_epoch=0)
        async with seeded["maker"]() as s:
            await pot_ownership_service.contribute_holding(s, seeded["pot"], user, investment_id=seeded["offered"])
        async with seeded["maker"]() as s:
            row = (await s.execute(text("SELECT user_id, pot_id FROM investments WHERE id = :i"), {"i": seeded["offered"]})).one()
            snapshot = (
                await s.execute(text("SELECT user_id, pot_id FROM investment_snapshots WHERE investment_id = :i"), {"i": seeded["offered"]})
            ).one()
        assert (row.user_id, row.pot_id) == (None, seeded["pot"])
        assert (snapshot.user_id, snapshot.pot_id) == (None, seeded["pot"])

    @pytest.mark.asyncio
    async def test_the_group_hears_about_it_once(self, seeded):
        # One audit entry, not two. The act changed two tables and a `holdings_added` entry beside the
        # movement would put two lines in the group's feed for a single thing that happened.
        user = User(id=seeded["user"], name="Santi", email=_EMAIL, password_hash="h", session_epoch=0)
        async with seeded["maker"]() as s:
            await pot_ownership_service.contribute_holding(s, seeded["pot"], user, investment_id=seeded["offered"])
        async with seeded["maker"]() as s:
            rows = (
                await s.execute(text("SELECT entity_type, action, payload FROM shared_audit_log WHERE group_id = :g"), {"g": seeded["group"]})
            ).all()
        assert len(rows) == 1
        assert (rows[0].entity_type, rows[0].action) == ("ownership_event", "created")
        assert rows[0].payload["variant"] == "contribution"
        assert (rows[0].payload["amount"], rows[0].payload["currency"]) == ("55.00", "USD")
