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
# still produce a self-consistent column, just one with an unexplained jump in it. Two things guard
# it, because the row set is stated in both places and nothing in the type system ties them together:
# the walk-down (the oldest row's balance_after minus its own amount must equal opening_balance), and
# tests/integration/test_account_ledger_drift.py, which asserts against a real Postgres that summing
# the union equals get_account_balances for every shape of movement. Unit tests cannot cover either —
# they mock the repositories, so a wrong query passes them.

import math

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.account_movement import MovementKind
from app.models.user import User
from app.repositories import account_movement_repository
from app.schemas.account_movement import AccountMovementListResponse, AccountMovementResponse
from app.services import account_service

# Ceiling on the requested page before any query is built. Python ints are unbounded, so an absurd
# `?page=` would otherwise reach Postgres as an OFFSET outside int64 and fail the whole request with a
# 500 — and it has to be applied BEFORE the first query, since that is what builds the offset. Any
# value above this is past the end of every conceivable ledger, so it lands on the real last page via
# the clamp below rather than being refused.
_MAX_PAGE = 1_000_000


# One page of an account's ledger, newest first. Verifies ownership.
#
# `page` is CLAMPED to the last page that has rows: a stale bookmark or a deletion that shortened the
# ledger would otherwise render "no movements yet" under a header showing a non-zero balance, with no
# page marked active in the pager.
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
    # In EITHER scope, unlike every other reader of this service: a group's bank account has a ledger
    # worth reading — it is how the household sees its own money move — and the balance beside it has
    # been dual-scope since 0019. Reachability is RLS's answer plus the pot's own predicate, which is
    # what get_account_in_scope defers to; nothing here writes.
    account = await account_service.get_account_in_scope(session, account_id, user)
    page = min(page, _MAX_PAGE)
    bounds = {"opening_date": account.opening_date, "pot_id": account.pot_id, "kind": kind, "page_size": page_size}
    rows, total = await account_movement_repository.list_movements(session, account_id, user.id, page=page, **bounds)

    # An empty result is either an empty ledger or a page past the end — only a count separates them,
    # so it is asked for exactly then, keeping the in-range case at one query.
    if not rows:
        total = await account_movement_repository.count_movements(
            session, account_id, user.id, opening_date=account.opening_date, pot_id=account.pot_id, kind=kind
        )
        if total:
            page = math.ceil(total / page_size)
            rows, total = await account_movement_repository.list_movements(session, account_id, user.id, page=page, **bounds)
        else:
            page = 1

    balance = None if kind is not None else await account_service.get_account_balance(session, account, user.id)
    # `running_total` is Σ amounts from the newest movement through this row, so undoing it against
    # the account's current balance — and re-adding the row's own amount, which the balance still
    # includes — lands exactly on the balance immediately after this movement.
    items = [
        AccountMovementResponse.model_validate(
            row.movement._replace(balance_after=None if balance is None else balance - row.running_total + row.movement.amount)
        )
        for row in rows
    ]

    return AccountMovementListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        currency=account.currency,
    )
