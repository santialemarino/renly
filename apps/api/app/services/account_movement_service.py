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
# account's opening_balance. Because every balance test mocks the repositories, that invariant is
# only meaningful against a real database and is verified there by hand (see the PR's live run) —
# the same gap the deferred e2e harness would close, and the reason the union's per-branch
# opening_date bound has to match the balance sums exactly.

import math
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.account_movement import AccountMovement, MovementKind, MovementSource
from app.models.user import User
from app.repositories import account_movement_repository
from app.schemas.account_movement import AccountMovementListResponse, AccountMovementResponse
from app.services import account_service


# One page of an account's ledger, newest first. Verifies ownership.
#
# `page` is CLAMPED to the last page that has rows: a stale bookmark or a deletion that shortened the
# ledger would otherwise render "no movements yet" under a header showing a non-zero balance, with no
# page marked active in the pager. Clamping also keeps the OFFSET bounded — Python ints are unbounded
# and a large enough page overflows the int64 bind parameter.
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
) -> AccountMovementListResponse:
    account = await account_service.get_account(session, account_id, user)
    total = await account_movement_repository.count_movements(session, account_id, user.id, kind=kind)
    page = min(page, max(1, math.ceil(total / page_size)))
    rows = await account_movement_repository.list_movements(session, account_id, user.id, kind=kind, page=page, page_size=page_size)

    running = None
    if kind is None:
        balance = await account_service.get_account_balance(session, account, user.id)
        newer = await account_movement_repository.sum_of_newer_movements(session, account_id, user.id, offset=(page - 1) * page_size)
        # The balance immediately after the page's FIRST row: everything newer than it, undone.
        running = balance - newer

    items = []
    for row in rows:
        movement = AccountMovement(
            source=MovementSource(row.source),
            source_id=row.source_id,
            kind=MovementKind(row.kind),
            date=row.date,
            amount=row.amount,
            balance_after=running,
            category=row.category,
            counterparty=row.counterparty,
            counterparty_amount=row.counterparty_amount,
            counterparty_currency=row.counterparty_currency,
            notes=row.notes,
        )
        items.append(AccountMovementResponse.model_validate(movement))
        if running is not None:
            running -= Decimal(row.amount)

    return AccountMovementListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        currency=account.currency,
    )
