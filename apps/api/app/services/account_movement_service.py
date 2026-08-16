# Per-account ledger: the unified, paginated list of every movement that reaches one account —
# income, expenses, card settlements, both transfer legs, and the reconciliation adjustments — each
# row carrying the account's balance immediately after it.
#
# THE RUNNING BALANCE IS DERIVED FROM THE ACCOUNTS PAGE'S OWN NUMBER, NOT RECOMPUTED. Renly already
# computes cash twice — account_service.get_account_summaries (the dashboard headline and the
# accounts table) and the compute_monthly_cash_balances siblings (the net-worth evolution chart) —
# and the two drifting apart has shipped as a real defect before. A ledger is a third reader of the
# same union, so it deliberately does NOT add a third answer: it takes the current balance from
# get_account_summaries and walks backwards through the page, subtracting each row. The top of the
# ledger is therefore the same number the accounts table shows, by construction rather than by
# agreement, and the only thing the union has to get right is which rows exist.
#
# That leaves one failure the anchoring cannot catch — a movement type missing from the union would
# still produce a self-consistent column, just one with an unexplained jump in it. The invariant that
# catches it is the walk-down: the oldest row's balance_after minus its own amount must equal the
# account's opening_balance. It is asserted in the tests and is why the union's per-branch
# opening_date bound has to match the balance sums exactly.

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.account_movement import AccountMovement, MovementKind
from app.models.user import User
from app.repositories import account_movement_repository
from app.services import account_service

ZERO = Decimal(0)


# One page of an account's ledger, newest first, plus the total for pagination. Verifies ownership.
#
# `balance_after` is populated only on the unfiltered ledger. Under a kind filter each row's balance
# would still be true, but consecutive visible rows would differ by amounts the filter hides, which
# reads as broken arithmetic — so the column is withheld rather than made to look wrong.
async def list_account_movements(
    session: AsyncSession,
    account_id: int,
    user: User,
    *,
    kind: MovementKind | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[AccountMovement], int, str]:
    account = await account_service.get_account(session, account_id, user)
    rows = await account_movement_repository.list_movements(session, account_id, user.id, kind=kind, page=page, page_size=page_size)
    total = await account_movement_repository.count_movements(session, account_id, user.id, kind=kind)

    running = None
    if kind is None:
        balances = await account_service.get_account_balances(session, [account], user.id)
        newer = await account_movement_repository.sum_of_newer_movements(session, account_id, user.id, offset=(page - 1) * page_size)
        # The balance immediately after the page's FIRST row: everything newer than it, undone.
        running = balances.get(account_id, account.opening_balance) - newer

    movements = []
    for row in rows:
        amount = Decimal(str(row.amount))
        movements.append(
            AccountMovement(
                source_id=row.source_id,
                kind=MovementKind(row.kind),
                date=row.date,
                amount=amount,
                balance_after=running,
                category=row.category,
                counterparty=row.counterparty,
                counterparty_amount=Decimal(str(row.counterparty_amount)) if row.counterparty_amount is not None else None,
                counterparty_currency=row.counterparty_currency,
                notes=row.notes,
            )
        )
        if running is not None:
            running -= amount

    return movements, total, account.currency
