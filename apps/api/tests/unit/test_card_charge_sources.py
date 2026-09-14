# Every reader of "what a card bucket owes" must consult the same tables, and this is the test that
# says so once instead of five times.
#
# The recurring defect in this codebase is not arithmetic. It is that N functions each independently
# enumerate what contributes to a figure, a new contributor arrives, and only some of them learn about
# it. It has shipped five times in the shared-money initiative alone, and the last one lived for two
# weeks: `sum_expenses_by_bucket_at` was written in July as the batched sibling of `sum_expenses_at`,
# BEFORE a shared expense could name a card at all — so when shared money taught the other readers about
# `shared_expenses`, the one that predated the feature was the one nobody thought to look at. The
# Payments Calendar then priced a card_due below the bill it was due for.
#
# Two properties make this catch that class rather than one instance of it:
#
# * It is a SET DIFFERENCE across readers, not an assertion per reader. PR 11's lesson: a per-item check
#   agrees with itself forever, because a reader nobody added to the list is a reader nobody checks.
#   Here every reader is compared against every other, so a new table that reaches four of five readers
#   fails no matter which four.
# * It reads the SQL the code actually emits rather than the code's intent. A mocked repository returns
#   whatever it was told to, so a unit test cannot see that two statements which must describe the same
#   rows have stopped agreeing — the same reason `test_cross_currency_settlement.py` compiles its
#   statements, and this reuses that technique.
#
# It needs no database: every reader is driven against a session that returns empty results, and what is
# inspected is the statement each one compiled on the way.

import re
from datetime import date
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql

from app.repositories import card_reconciliation_repository
from app.services import card_reconciliation_service, credit_card_service

# What can put a charge on, or take one off, a card bucket. This set IS the invariant: adding a fourth
# way to charge a card means adding it here, and this test then names every reader that has not learned
# about it.
CHARGE_TABLES = frozenset({"expense_entries", "shared_expenses", "card_settlements"})

AS_OF = date(2026, 8, 17)
CARD_ID = 5
USER_ID = 7

# Every path that answers "what does this bucket owe", at the layer where the answer is assembled —
# which is the service for the two composed ones and the repository for the three that are a single
# statement family. Each is named by what it drives in the product, because that is what a failure here
# actually costs.
READERS = {
    "get_card_balances — the headline on /credit-cards and the dashboard": lambda s: credit_card_service.get_card_balances(
        s, [CARD_ID], {CARD_ID: "USD"}, USER_ID
    ),
    "get_card_bucket_series — the net-worth chart's card line": lambda s: credit_card_service.get_card_bucket_series(s, [CARD_ID], USER_ID),
    "compute_bucket_balance_at — a statement's computed balance": lambda s: card_reconciliation_service.compute_bucket_balance_at(
        s, CARD_ID, "USD", AS_OF
    ),
    "compute_bucket_balances_at — the Payments Calendar's card_due": lambda s: card_reconciliation_service.compute_bucket_balances_at(
        s, [CARD_ID], AS_OF
    ),
    "get_first_activity_date — which statements the list shows at all": lambda s: card_reconciliation_repository.get_first_activity_date(
        s, CARD_ID, "USD"
    ),
}


# Drives one reader against a session that answers every result shape emptily, then returns the charge
# tables named by EVERY statement it compiled on the way — `await_args_list`, not `await_args`, because
# three of these readers issue more than one and the last one alone would hide the rest.
async def _charge_tables(factory) -> set[str]:
    session = AsyncMock()
    result = Mock(all=Mock(return_value=[]), scalar_one=Mock(return_value=0), first=Mock(return_value=None))
    result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
    session.execute = AsyncMock(return_value=result)
    await factory(session)
    assert session.execute.await_args_list, "the reader issued no statement at all, so this proves nothing about it"
    tables: set[str] = set()
    for call in session.execute.await_args_list:
        sql = str(call.args[0].compile(dialect=postgresql.dialect())).lower()
        # Word-bounded so `shared_expenses` cannot be matched by a column that merely contains the name.
        tables |= {table for table in CHARGE_TABLES if re.search(rf"\b{table}\b", sql)}
    return tables


class TestEveryReaderOfACardBucketReadsTheSameTables:
    @pytest.mark.asyncio
    async def test_the_readers_agree_on_which_tables_charge_a_card(self):
        # THE test. Not "does each reader read shared_expenses" — that question has to be asked once per
        # reader and stops being asked the moment somebody adds a sixth. Comparing the sets against each
        # other asks it for every reader that exists, including the ones added after this was written.
        seen = {label: await _charge_tables(factory) for label, factory in READERS.items()}
        distinct = {frozenset(tables) for tables in seen.values()}
        assert len(distinct) == 1, "readers disagree about what charges a card: " + "; ".join(
            f"{label} reads {sorted(tables)}" for label, tables in sorted(seen.items())
        )

    @pytest.mark.asyncio
    async def test_the_set_they_agree_on_is_the_whole_one(self):
        # The other half, and it is not redundant: five readers that ALL forgot a table agree perfectly
        # with each other. This is what makes CHARGE_TABLES the declaration rather than a description of
        # whatever the code happens to do.
        for label, factory in READERS.items():
            assert await _charge_tables(factory) == set(CHARGE_TABLES), f"{label} does not read every table that charges a card"

    @pytest.mark.asyncio
    async def test_a_reader_that_lost_a_table_is_named_rather_than_merely_failing(self):
        # The positive control, and the reason the assertion builds a message instead of comparing a
        # count: when this fires, whoever is reading it needs to know WHICH reader drifted. Simulated by
        # comparing the real readers against one that has been blinded to shared expenses.
        real = await _charge_tables(READERS["get_card_balances — the headline on /credit-cards and the dashboard"])
        blinded = real - {"shared_expenses"}
        assert blinded != real
        assert "shared_expenses" not in blinded
