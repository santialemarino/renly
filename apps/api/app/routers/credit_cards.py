from decimal import Decimal

from fastapi import APIRouter, Query, status

from app.deps.api_key_auth import JwtOrApiKeyUser
from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.domain import CardBucketBalance
from app.schemas.card_reconciliation import (
    CardReconciliationCreate,
    CardReconciliationResponse,
    StatementPeriodResponse,
)
from app.schemas.card_settlement import CardSettlementCreate, CardSettlementResponse
from app.schemas.credit_card import CardBucketBalanceResponse, CreditCardCreate, CreditCardResponse, CreditCardUpdate
from app.services import card_reconciliation_service, credit_card_service

router = APIRouter(prefix="/credit-cards", tags=["credit-cards"])


# Builds a CreditCardResponse with per-currency bucket balances and the has_expenses flag.
# `buckets` is empty when the card has no activity yet — the service still seeds the primary
# bucket with 0, so an empty list here means we're rendering pre-load (e.g. a fresh POST).
def _to_response(card: object, buckets: list[CardBucketBalance], has_expenses: bool = False) -> CreditCardResponse:
    from app.models.credit_card import CreditCard as CreditCardModel

    data = card.model_dump() if isinstance(card, CreditCardModel) else dict(card)  # type: ignore[arg-type]
    bucket_payload = [CardBucketBalanceResponse(currency=b.currency, balance=b.balance) for b in buckets]
    if not bucket_payload:
        # Fallback for the create-flow response: surface a zero bucket in the card's primary currency.
        bucket_payload = [CardBucketBalanceResponse(currency=data["currency"], balance=Decimal(0))]
    return CreditCardResponse(**{**data, "balances": bucket_payload, "has_expenses": has_expenses})


# --- Credit cards ---


# List credit cards for the current user with optional search, sorting, and balances.
@router.get("", response_model=list[CreditCardResponse])
async def list_cards(
    current_user: JwtOrApiKeyUser,
    session: SessionDep,
    search: str | None = Query(default=None, description="Filter cards by name (case-insensitive)."),
    sort_by: str | None = Query(default=None, description="Column to sort by (name, closing_day, due_day, currency)."),
    sort_order: str = Query(default="asc", description="Sort direction (asc or desc)."),
    show_archived: bool = Query(default=False, description="Include archived (inactive) cards."),
) -> list[CreditCardResponse]:
    cards = await credit_card_service.list_cards(
        session,
        current_user,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=not show_archived,
    )
    card_ids = [c.id for c in cards if c.id is not None]
    card_currencies = {c.id: c.currency for c in cards if c.id is not None}
    balances = await credit_card_service.get_card_balances(session, card_ids, card_currencies, current_user.id)
    has_expenses = await credit_card_service.cards_have_expenses(session, card_ids, current_user.id)
    return [_to_response(card, balances.get(card.id, []), has_expenses.get(card.id, False)) for card in cards]


# Get a single credit card with its current balance.
@router.get("/{card_id}", response_model=CreditCardResponse)
async def get_card(
    card_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> CreditCardResponse:
    card = await credit_card_service.get_card(session, card_id, current_user)
    balances = await credit_card_service.get_card_balances(session, [card.id], {card.id: card.currency}, current_user.id)
    has_expenses = await credit_card_service.cards_have_expenses(session, [card.id], current_user.id)
    return _to_response(card, balances.get(card.id, []), has_expenses.get(card.id, False))


# Create a new credit card.
@router.post("", response_model=CreditCardResponse, status_code=status.HTTP_201_CREATED)
async def create_card(
    body: CreditCardCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> CreditCardResponse:
    card = await credit_card_service.create_card(
        session,
        current_user,
        name=body.name,
        closing_day=body.closing_day,
        due_day=body.due_day,
        currency=body.currency,
        monthly_payment=body.monthly_payment,
        default_account_id=body.default_account_id,
    )
    return _to_response(card, [], False)


# Update a credit card.
@router.put("/{card_id}", response_model=CreditCardResponse)
async def update_card(
    card_id: int,
    body: CreditCardUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> CreditCardResponse:
    payload = body.model_dump(exclude_unset=True)
    card = await credit_card_service.update_card(session, card_id, current_user, **payload)
    balances = await credit_card_service.get_card_balances(session, [card.id], {card.id: card.currency}, current_user.id)
    has_expenses = await credit_card_service.cards_have_expenses(session, [card.id], current_user.id)
    return _to_response(card, balances.get(card.id, []), has_expenses.get(card.id, False))


# Delete a credit card. Rejects with 409 if the card has linked expenses.
@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(
    card_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await credit_card_service.delete_card(session, card_id, current_user)


# Archive a credit card (set is_active = false). Returns the updated card.
@router.post("/{card_id}/archive", response_model=CreditCardResponse)
async def archive_card(
    card_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> CreditCardResponse:
    card = await credit_card_service.archive_card(session, card_id, current_user)
    balances = await credit_card_service.get_card_balances(session, [card.id], {card.id: card.currency}, current_user.id)
    has_expenses = await credit_card_service.cards_have_expenses(session, [card.id], current_user.id)
    return _to_response(card, balances.get(card.id, []), has_expenses.get(card.id, False))


# Unarchive a credit card (set is_active = true). Returns the updated card.
@router.post("/{card_id}/unarchive", response_model=CreditCardResponse)
async def unarchive_card(
    card_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> CreditCardResponse:
    card = await credit_card_service.unarchive_card(session, card_id, current_user)
    balances = await credit_card_service.get_card_balances(session, [card.id], {card.id: card.currency}, current_user.id)
    has_expenses = await credit_card_service.cards_have_expenses(session, [card.id], current_user.id)
    return _to_response(card, balances.get(card.id, []), has_expenses.get(card.id, False))


# --- Settlements ---


# List settlements for a credit card, each naming the account it was paid from (when linked).
@router.get("/{card_id}/settlements", response_model=list[CardSettlementResponse])
async def list_settlements(
    card_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> list[CardSettlementResponse]:
    return await credit_card_service.list_settlements(session, card_id, current_user)


# Record a new settlement for a credit card.
@router.post(
    "/{card_id}/settlements",
    response_model=CardSettlementResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_settlement(
    card_id: int,
    body: CardSettlementCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> CardSettlementResponse:
    return await credit_card_service.create_settlement(
        session,
        card_id,
        current_user,
        date=body.date,
        amount=body.amount,
        currency=body.currency,
        account_id=body.account_id,
        account_amount=body.account_amount,
        notes=body.notes,
    )


# Delete a settlement. Returns 204.
@router.delete("/{card_id}/settlements/{settlement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_settlement(
    card_id: int,
    settlement_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await credit_card_service.delete_settlement(session, card_id, settlement_id, current_user)


# --- Reconciliations (Phase 3, Step 5) ---


# List reconciliations for a card. Optional ?currency= filters to a single bucket.
@router.get("/{card_id}/reconciliations", response_model=list[CardReconciliationResponse])
async def list_reconciliations(
    card_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    currency: str | None = Query(default=None, description="Filter to a single bucket currency."),
) -> list[CardReconciliationResponse]:
    rows = await card_reconciliation_service.list_reconciliations(session, card_id, current_user, currency=currency)
    return [CardReconciliationResponse.model_validate(r) for r in rows]


# List recent statement periods per bucket with reconciliation status. Drives the Reconciliations sub-section UI.
@router.get("/{card_id}/statements", response_model=list[StatementPeriodResponse])
async def list_statements(
    card_id: int,
    current_user: CurrentUser,
    session: SessionDep,
    currency: str = Query(description="Bucket currency to list statements for."),
) -> list[StatementPeriodResponse]:
    card = await credit_card_service.get_card(session, card_id, current_user)
    statements = await card_reconciliation_service.list_recent_statements(session, card, currency)
    return [
        StatementPeriodResponse(
            currency=s["currency"],
            period_start=s["period_start"],
            period_end=s["period_end"],
            computed_balance=s["computed_balance"],
            reconciliation=(CardReconciliationResponse.model_validate(s["reconciliation"]) if s["reconciliation"] is not None else None),
        )
        for s in statements
    ]


# Create-or-replace a reconciliation for (card, currency, period). Atomic.
@router.post(
    "/{card_id}/reconciliations",
    response_model=CardReconciliationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_or_replace_reconciliation(
    card_id: int,
    body: CardReconciliationCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> CardReconciliationResponse:
    rec = await card_reconciliation_service.create_or_replace(
        session,
        card_id,
        current_user,
        currency=body.currency,
        period_start=body.period_start,
        period_end=body.period_end,
        statement_balance=body.statement_balance,
    )
    return CardReconciliationResponse.model_validate(rec)


# Delete a reconciliation. Cascades to its adjustment expense or income.
@router.delete(
    "/{card_id}/reconciliations/{reconciliation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_reconciliation(
    card_id: int,
    reconciliation_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await card_reconciliation_service.delete_reconciliation(session, card_id, reconciliation_id, current_user)
