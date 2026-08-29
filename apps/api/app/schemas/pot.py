from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.pot import OwnershipEventType, PotVisibility
from app.schemas.base import RequestBase, validate_supported_currency


# Body for POST /pots.
class PotCreate(RequestBase):
    group_id: int = Field(description="Group the pot belongs to; the caller must be one of its admins.")
    name: str | None = Field(default=None, description="Optional label; a group's first pot needs none.", max_length=255)
    base_currency: str = Field(description="Currency all ownership math runs in (ISO 4217).", max_length=3)
    visibility: PotVisibility = Field(
        default=PotVisibility.members, description="Who sees it by default: every member, or only those granted access."
    )

    _validate_currency = field_validator("base_currency")(validate_supported_currency)


# Body for PUT /pots/{pot_id}. Partial update; only provided fields are updated.
# base_currency is deliberately absent: it is the unit of every figure already recorded in the
# ledger, so changing it would silently restate every past event at a rate nobody chose.
class PotUpdate(RequestBase):
    name: str | None = Field(default=None, description="Optional label.", max_length=255)
    visibility: PotVisibility | None = Field(default=None, description="Who sees it by default.")


# Body for PUT /pots/{pot_id}/permissions/{member_id}.
class PotPermissionUpdate(RequestBase):
    can_view: bool = Field(description="Whether this seat may see the pot at all.")
    can_write: bool = Field(default=False, description="Whether this seat may record movements; forces can_view.")


# One member's share of a pot: units held, the percentage they represent, and what that is worth.
# Percentages across a pot sum to exactly 100 and values to exactly the NAV — the rounding remainder
# is assigned to the largest holder rather than left to make the parts visibly disagree.
class PotMemberShareResponse(BaseModel):
    model_config = {"from_attributes": True}

    member_id: int = Field(description="Seat this share belongs to.")
    display_name: str = Field(description="How that person is shown in the group.")
    units: Decimal = Field(description="Units held after replaying the ledger.")
    percentage: Decimal = Field(description="Share of the pot, to two decimals.")
    value: Decimal | None = Field(default=None, description="Share value in the pot's base currency; null when the NAV is unknown.")
    is_self: bool = Field(description="Whether this is the requesting user's own seat.")


# One member's access to a pot. Present for every explicit permission row; a member with no row
# follows the pot's visibility default and does not appear here.
class PotPermissionResponse(BaseModel):
    model_config = {"from_attributes": True}

    member_id: int = Field(description="Seat this permission belongs to.")
    display_name: str = Field(description="How that person is shown in the group.")
    can_view: bool = Field(description="Whether this seat may see the pot.")
    can_write: bool = Field(description="Whether this seat may record movements.")


# Response for GET list and GET one, POST and PUT.
# nav and unit_price are null when the pot has no valuation — a pot with no holdings, or one whose
# currency cannot be converted. Null rather than zero: "we do not know" and "it is worth nothing" are
# different answers, and only one of them is safe to price units against.
class PotResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int = Field(description="Pot id.")
    group_id: int = Field(description="Group whose members can reach it.")
    name: str | None = Field(default=None, description="Label; null for a group's default pot.")
    base_currency: str = Field(description="Currency all ownership math runs in.")
    visibility: PotVisibility = Field(description="Who sees it by default.")
    is_default: bool = Field(description="Whether this is the group's first pot.")
    nav: Decimal | None = Field(default=None, description="Value of everything the pot holds, in its base currency.")
    unit_price: Decimal | None = Field(default=None, description="NAV divided by units outstanding; null when either is unknown.")
    total_units: Decimal = Field(description="Units outstanding across every owner.")
    my_percentage: Decimal = Field(description="The requesting user's own share, to two decimals; zero when they own none.")
    can_write: bool = Field(description="Whether the requesting user may record movements.")
    shares: list[PotMemberShareResponse] = Field(description="Ownership breakdown, largest holder first.")
    permissions: list[PotPermissionResponse] = Field(description="Explicit per-member access rows.")
    created_at: datetime = Field(description="When the pot was created.")
    updated_at: datetime = Field(description="When the pot was last changed.")


# One thing a pot holds: an investment or a cash account, and what it is worth.
#
# `value` is in the holding's OWN currency; `base_value` is the same figure converted to the pot's
# base currency, which is what makes it comparable to the NAV. Both are null when unknown rather than
# zero — an investment with no snapshot yet, or a currency with no stored rate on the date — because
# "we do not know" and "it is worth nothing" are different answers.
#
# Archived holdings are listed too, flagged by `is_active`. An archived holding still points at the
# pot, so it still blocks deleting it and still has to be movable back out; it contributes nothing to
# the NAV, so its figures are its own last-known value and not a claim about the pot's.
class PotHoldingResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int = Field(description="Investment or account id.")
    name: str = Field(description="How the holding is shown.")
    currency: str = Field(description="The holding's own currency.")
    value: Decimal | None = Field(default=None, description="Latest known value in the holding's own currency; null when unknown.")
    base_value: Decimal | None = Field(default=None, description="The same figure in the pot's base currency; null when unknown or unconvertible.")
    is_active: bool = Field(description="Whether the holding is active; an archived one contributes nothing to the NAV.")


# Response for GET /pots/{pot_id}/holdings. Split into the same two lists the move endpoints take as
# input, so what a client reads back and what it posts have one shape rather than two.
class PotHoldingsResponse(BaseModel):
    investments: list[PotHoldingResponse] = Field(description="Investments the pot holds, by name.")
    accounts: list[PotHoldingResponse] = Field(description="Cash accounts the pot holds, by name.")


# Body for POST and DELETE /pots/{pot_id}/holdings — moving stock into or out of a pot.
# Both lists are optional so one call can move investments, accounts, or both together; naming
# neither is a no-op rather than an error, because the guided flows build the payload from what the
# user selected and an empty selection is not a mistake worth a 422.
class PotHoldingsMove(RequestBase):
    investment_ids: list[int] = Field(default_factory=list, description="Investments to move.")
    account_ids: list[int] = Field(default_factory=list, description="Accounts to move.")


# Body for POST /pots/{pot_id}/ownership/opening.
# The percentages ARE the agreement, so they are taken as entered and refused when they do not total
# 100 rather than quietly rescaled.
class PotOpeningCreate(RequestBase):
    date: date_type = Field(description="Date the baseline is measured at; nothing before it is in scope.")
    value: Decimal = Field(description="What the pot was worth on that date, in its base currency.", max_digits=18, decimal_places=2, gt=0)
    shares: dict[int, Decimal] = Field(description="Percentage per group member id; must total 100.")
    notes: str | None = Field(default=None, description="Optional notes.")


# Body for POST /pots/{pot_id}/ownership/movements — a contribution or a withdrawal.
# Both account legs are optional: money can arrive from outside Renly, or land in a holding that is an
# investment rather than a tracked account.
class PotMovementCreate(RequestBase):
    type: OwnershipEventType = Field(description="contribution or withdrawal; opening and reagreement have their own endpoints.")
    date: date_type = Field(description="Date the movement is priced at.")
    member_id: int = Field(description="Seat whose units change.")
    amount: Decimal = Field(description="Money moved, in the source account's currency.", max_digits=18, decimal_places=2, gt=0)
    amount_currency: str | None = Field(default=None, description="Source currency; defaults to the pot's.", max_length=3)
    base_amount: Decimal | None = Field(
        default=None,
        description="Credited amount in the pot's base currency; required when currencies differ.",
        max_digits=18,
        decimal_places=2,
        gt=0,
    )
    from_account_id: int | None = Field(default=None, description="Account debited: the mover's own on a contribution.")
    to_account_id: int | None = Field(default=None, description="Account credited: one the pot holds on a contribution.")
    whole_share: bool = Field(
        default=False,
        description="Withdrawal only: redeem exactly the member's whole balance instead of deriving units from the amount.",
    )
    notes: str | None = Field(default=None, description="Optional notes.")

    _validate_currency = field_validator("amount_currency")(validate_supported_currency)

    # `whole_share` is a withdrawal's concept only: it redeems units the member already holds, and a
    # contribution issues units from money instead — there is no share to take the whole of. Refused
    # at the request boundary rather than as a coded domain refusal, the same way ExpenseCreate refuses
    # two commitment links: it is a malformed body, not a rule about this pot, and no surface in the
    # app can produce it (the guided flow that sets the flag records withdrawals only).
    @model_validator(mode="after")
    def validate_whole_share_is_a_withdrawal(self) -> "PotMovementCreate":
        if self.whole_share and self.type != OwnershipEventType.withdrawal:
            raise ValueError("whole_share applies to a withdrawal only.")
        return self


# Body for POST /pots/{pot_id}/ownership/reagreements — units moving between two members, no money.
#
# The share moved is stated one of two ways, and exactly one of them: `percentage` of the whole pot, or
# `whole_share` for the giver's entire balance. The second is not sugar for `percentage=<their share>`
# — a share rounded to NUMERIC(5,2) and multiplied back out lands on the giver's exact balance almost
# never (measured over 200,000 plausible pots: 18 times), leaving them either refused or holding a
# residual that reads as a 0.00% owner forever.
class PotReagreementCreate(RequestBase):
    date: date_type = Field(description="Date the transfer of units is priced at.")
    from_member_id: int = Field(description="Seat giving up units.")
    to_member_id: int = Field(description="Seat receiving them.")
    percentage: Decimal | None = Field(
        default=None, description="How much of the whole pot moves, in percentage points.", max_digits=5, decimal_places=2, gt=0
    )
    whole_share: bool = Field(default=False, description="Move the giver's entire balance instead of a percentage of the pot.")
    notes: str | None = Field(default=None, description="Optional notes.")

    # Exactly one of the two ways to state the share. Neither means nothing was said; both means two
    # answers to one question, and silently preferring one would discard a figure the caller typed.
    @model_validator(mode="after")
    def validate_share_stated_once(self) -> "PotReagreementCreate":
        if self.whole_share == (self.percentage is not None):
            raise ValueError("State the share moved as either percentage or whole_share, not both and not neither.")
        return self


# Response for the ownership ledger list and for each movement endpoint.
class PotOwnershipEventResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int = Field(description="Event id.")
    pot_id: int = Field(description="Pot whose ownership this moved.")
    type: OwnershipEventType = Field(description="What the entry records.")
    date: date_type = Field(description="Date it is priced at.")
    member_id: int = Field(description="Seat whose units changed.")
    member_name: str = Field(description="How that person is shown in the group.")
    counterparty_member_id: int | None = Field(default=None, description="Reagreement only: the seat on the other side.")
    counterparty_name: str | None = Field(default=None, description="Reagreement only: how that person is shown.")
    amount: Decimal | None = Field(default=None, description="Money moved, in its source currency.")
    amount_currency: str | None = Field(default=None, description="Source currency; null when it equals the pot's.")
    base_amount: Decimal | None = Field(default=None, description="Credited amount in the pot's base currency.")
    units: Decimal = Field(description="Signed change to the member's unit balance.")
    unit_price: Decimal = Field(description="The price used, as at the event's date.")
    from_account_id: int | None = Field(default=None, description="Account debited.")
    to_account_id: int | None = Field(default=None, description="Account credited.")
    notes: str | None = Field(default=None, description="Optional notes.")
    created_at: datetime = Field(description="When it was recorded.")
