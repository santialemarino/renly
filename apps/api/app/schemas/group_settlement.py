# Request/response schemas for a group's balances and the settlements that clear them.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.group_money_settings import SplitMethod
from app.models.group_settlement import GroupSettlementStatus
from app.schemas.base import RequestBase, validate_supported_currency


# Body for POST /groups/{group_id}/settlements — a payment one member made to another.
#
# `amount`/`currency` name the BUCKET being cleared. The two cash legs are each optional and each
# belongs to one side: the payer says what left their account, the payee what arrived in theirs. Both
# may be omitted, which is mark-as-paid with no account named — the v1 default, and the only thing a
# name-only member's side can ever be.
#
# A leg's amount is only needed when that account's currency differs from the bucket's. When they
# match, what left the account IS what cleared the bucket, so a second copy of the same figure would
# be a second thing to keep in step.
class GroupSettlementCreate(RequestBase):
    from_member_id: int = Field(description="Seat paying.")
    to_member_id: int = Field(description="Seat being paid.")
    date: date_type = Field(description="Date the payment happened.")
    amount: Decimal = Field(description="Amount cleared off the balance.", gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(description="The bucket's currency (ISO 4217).", max_length=3)
    from_account_id: int | None = Field(default=None, description="Account the payer drew from; must be their own.")
    from_amount: Decimal | None = Field(
        default=None, description="What left that account, in its currency. Required only across currencies.", gt=0, max_digits=18, decimal_places=2
    )
    to_account_id: int | None = Field(default=None, description="Account the payee received into; must be their own.")
    to_amount: Decimal | None = Field(
        default=None, description="What arrived there, in its currency. Required only across currencies.", gt=0, max_digits=18, decimal_places=2
    )
    notes: str | None = Field(default=None, description="Optional notes.", max_length=500)

    _validate_currency = field_validator("currency")(validate_supported_currency)


# Body for POST /groups/{group_id}/settlements/write-off — a debt the creditor gives up on.
# It clears the same bucket a payment would and moves no money, so it names no account and carries no
# cash leg; only the person who is owed may record one.
class GroupWriteOffCreate(RequestBase):
    from_member_id: int = Field(description="Seat whose debt is being forgiven.")
    to_member_id: int = Field(description="Seat giving up the claim; must be the caller's own.")
    date: date_type = Field(description="Date the balance was written off.")
    amount: Decimal = Field(description="Amount written off.", gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(description="The bucket's currency (ISO 4217).", max_length=3)
    notes: str | None = Field(default=None, description="Optional notes.", max_length=500)

    _validate_currency = field_validator("currency")(validate_supported_currency)


# Body for PUT /groups/{group_id}/settlements/{settlement_id}/account — the caller's OWN cash leg.
#
# One body for both sides: which leg it lands on follows from which seat the caller holds, so nothing
# here names a side and nothing can name the other person's. A null account_id clears the leg.
class GroupSettlementLegUpdate(RequestBase):
    account_id: int | None = Field(default=None, description="The caller's own account the money moved through; null clears the leg.")
    amount: Decimal | None = Field(
        default=None, description="What moved through it, in its currency. Required only across currencies.", gt=0, max_digits=18, decimal_places=2
    )


# One recorded settlement or write-off.
class GroupSettlementResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int = Field(description="Settlement id.")
    group_id: int = Field(description="Group whose balance it clears.")
    from_member_id: int = Field(description="Seat paying.")
    from_display_name: str = Field(description="That person's name.")
    to_member_id: int = Field(description="Seat being paid.")
    to_display_name: str = Field(description="That person's name.")
    date: date_type = Field(description="Date the payment happened.")
    amount: Decimal = Field(description="Amount cleared off the balance.")
    currency: str = Field(description="The bucket's currency.")
    status: GroupSettlementStatus = Field(description="pending, confirmed, or written_off.")
    from_account_id: int | None = Field(default=None, description="Account the payer drew from.")
    from_amount: Decimal | None = Field(default=None, description="What left it, when that crossed currencies.")
    to_account_id: int | None = Field(default=None, description="Account the payee received into.")
    to_amount: Decimal | None = Field(default=None, description="What arrived there, when that crossed currencies.")
    confirmed_at: datetime | None = Field(default=None, description="When the payee acknowledged receipt.")
    notes: str | None = Field(default=None, description="Optional notes.")
    can_confirm: bool = Field(description="Whether the requesting user is the payee of a settlement still awaiting confirmation.")
    can_delete: bool = Field(description="Whether the requesting user may remove it — either party while pending, the creditor for a write-off.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")


# One member's standing in one currency: positive means they are owed, negative means they owe.
class GroupMemberBalanceResponse(BaseModel):
    model_config = {"from_attributes": True}

    member_id: int = Field(description="Seat this position belongs to.")
    display_name: str = Field(description="How that person is shown in the group.")
    amount: Decimal = Field(description="Positive when owed, negative when owing.")
    is_self: bool = Field(description="Whether this is the requesting user's own seat.")


# One suggested payment from the settle-up plan.
class GroupSettleSuggestionResponse(BaseModel):
    model_config = {"from_attributes": True}

    from_member_id: int = Field(description="Seat that should pay.")
    from_display_name: str = Field(description="That person's name.")
    to_member_id: int = Field(description="Seat that should be paid.")
    to_display_name: str = Field(description="That person's name.")
    amount: Decimal = Field(description="How much to pay.")


# One currency's balances, and the fewest payments that clear them.
#
# A bucket per currency, never netted against another: owing dollars while being owed pesos is a real
# state, and merging them would invent a rate nobody agreed to. The converted total beside each is for
# reading at a glance only — it is never what anybody settles.
class GroupCurrencyBalanceResponse(BaseModel):
    model_config = {"from_attributes": True}

    currency: str = Field(description="The bucket's currency (ISO 4217).")
    balances: list[GroupMemberBalanceResponse] = Field(description="Every member with a non-zero position, largest creditor first.")
    suggestions: list[GroupSettleSuggestionResponse] = Field(description="The fewest payments that clear this bucket.")
    my_balance: Decimal = Field(description="The requesting user's own position in this bucket; zero when they are square.")
    my_converted_balance: Decimal | None = Field(
        default=None, description="That position in the requested display currency; null when no rate is available."
    )


# Response for GET /groups/{group_id}/balances.
class GroupBalancesResponse(BaseModel):
    model_config = {"from_attributes": True}

    group_id: int = Field(description="Group these balances belong to.")
    buckets: list[GroupCurrencyBalanceResponse] = Field(description="One per currency the group has money in, alphabetical.")
    display_currency: str | None = Field(default=None, description="Target currency for the converted totals (None = original).")
    skipped_currencies: list[str] = Field(default_factory=list, description="Currencies with no usable rate to the display currency.")


# Body for PUT /groups/{group_id}/money-settings. Partial update; only provided fields are changed.
class GroupMoneySettingsUpdate(RequestBase):
    default_split_method: SplitMethod | None = Field(default=None, description="The split a new shared expense starts on.")
    auto_finalise_settlements: bool | None = Field(
        default=None, description="When true a recorded settlement is confirmed on the spot instead of waiting on the payee."
    )


# The money settings a group holds in common.
class GroupMoneySettingsResponse(BaseModel):
    model_config = {"from_attributes": True}

    group_id: int = Field(description="Group these settings belong to.")
    default_split_method: SplitMethod = Field(description="The split a new shared expense starts on.")
    auto_finalise_settlements: bool = Field(description="Whether a recorded settlement is confirmed on the spot.")
