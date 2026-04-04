from decimal import Decimal

from fastapi import APIRouter, Query, status

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.card_settlement import CardSettlementCreate, CardSettlementResponse
from app.schemas.credit_card import CreditCardCreate, CreditCardResponse, CreditCardUpdate
from app.services import credit_card_service

router = APIRouter(prefix="/credit-cards", tags=["credit-cards"])


# Builds a CreditCardResponse with the computed balance field.
def _to_response(card: object, balance: Decimal) -> CreditCardResponse:
    from app.models.credit_card import CreditCard as CreditCardModel

    data = card.model_dump() if isinstance(card, CreditCardModel) else dict(card)  # type: ignore[arg-type]
    return CreditCardResponse(**{**data, "balance": balance})


# --- Credit cards ---


# List credit cards for the current user with optional search, sorting, and balances.
@router.get("", response_model=list[CreditCardResponse])
async def list_cards(
    current_user: CurrentUser,
    session: SessionDep,
    search: str | None = Query(default=None, description="Filter cards by name (case-insensitive)."),
    sort_by: str | None = Query(default=None, description="Column to sort by (name, closing_day, due_day, currency)."),
    sort_order: str = Query(default="asc", description="Sort direction (asc or desc)."),
) -> list[CreditCardResponse]:
    cards = await credit_card_service.list_cards(
        session,
        current_user,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    card_ids = [c.id for c in cards if c.id is not None]
    balances = await credit_card_service.get_card_balances(session, card_ids)
    return [_to_response(card, balances.get(card.id, Decimal(0))) for card in cards]


# Get a single credit card with its current balance.
@router.get("/{card_id}", response_model=CreditCardResponse)
async def get_card(
    card_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> CreditCardResponse:
    card = await credit_card_service.get_card(session, card_id, current_user)
    balance = await credit_card_service.get_card_balance(session, card.id)
    return _to_response(card, balance)


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
    )
    return _to_response(card, Decimal(0))


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
    balance = await credit_card_service.get_card_balance(session, card.id)
    return _to_response(card, balance)


# Delete a credit card. Returns 204.
@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(
    card_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await credit_card_service.delete_card(session, card_id, current_user)


# --- Settlements ---


# List settlements for a credit card.
@router.get("/{card_id}/settlements", response_model=list[CardSettlementResponse])
async def list_settlements(
    card_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> list[CardSettlementResponse]:
    settlements = await credit_card_service.list_settlements(session, card_id, current_user)
    return [CardSettlementResponse.model_validate(s) for s in settlements]


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
    settlement = await credit_card_service.create_settlement(
        session,
        card_id,
        current_user,
        date=body.date,
        amount=body.amount,
        currency=body.currency,
        notes=body.notes,
    )
    return CardSettlementResponse.model_validate(settlement)


# Delete a settlement. Returns 204.
@router.delete("/{card_id}/settlements/{settlement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_settlement(
    card_id: int,
    settlement_id: int,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await credit_card_service.delete_settlement(session, card_id, settlement_id, current_user)
