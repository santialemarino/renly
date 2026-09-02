# Request/response schemas for a group's shared income.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.group_money_settings import SplitMethod
from app.models.income_entry import IncomeCategory
from app.models.shared_income import IncomeDestination
from app.schemas.base import RequestBase, validate_supported_currency, validate_user_pickable_income_category


# One participant's line in a split. `figure` is the figure the chosen method needs and nothing else:
# ignored by `equal`, an amount for `exact`, a weight for `shares`, a percentage for `percentage`. One
# field rather than three, because exactly one is ever meaningful and three would allow a body where
# two are set and neither is authoritative.
class SharedIncomeSplitInput(RequestBase):
    member_id: int = Field(description="Seat taking a share of this income.")
    figure: Decimal | None = Field(default=None, description="Amount, weight or percentage, per the split method.", max_digits=18, decimal_places=2)


# Body for POST /groups/{group_id}/income.
#
# `destination` says WHERE the money ended up and `received_by_member_id` says WHO holds it; the two
# are one question answered on two branches rather than two independent fields:
#   * `joint` — it landed in a shared account a pot holds, so the pot's owners received it in their own
#     proportions. `paid_to_account_id` is required (a CHECK enforces the shape and the service checks
#     the account is really this group's), and naming a recipient is refused, because saying one member
#     received joint money asserts something the ownership ledger contradicts.
#   * `distributed` — it reached one person. `received_by_member_id` is required; `paid_to_account_id`
#     is optional and, when given, must be that member's own private account.
#
# `source_investment_id` is the co-owned asset the income came from. It drives the DEFAULT split the
# form pre-fills (F1) and is stored as the row's label; it never changes what the API computes, which
# is always the split the request states.
class SharedIncomeCreate(RequestBase):
    date: date_type = Field(description="Income date.")
    amount: Decimal = Field(description="Full amount received, before any split.", gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(description="Currency (ISO 4217); also the balance bucket this lands in.", max_length=3)
    category: IncomeCategory | None = Field(default=None, description="Income category.")
    notes: str | None = Field(default=None, description="Optional notes.", max_length=500)
    split_method: SplitMethod = Field(description="How the total is divided between the participants.")
    splits: list[SharedIncomeSplitInput] = Field(description="Who takes a share, and their figure for the chosen method.", min_length=1)
    destination: IncomeDestination = Field(description="Whether the money stays joint in a pot or is distributed to one person.")
    source_investment_id: int | None = Field(default=None, description="Co-owned asset this came from; must be one this group's pots hold.")
    received_by_member_id: int | None = Field(default=None, description="Seat the money reached; required for distributed, refused for joint.")
    paid_to_account_id: int | None = Field(default=None, description="Account the money arrived in: one a pot holds, or the recipient's own.")

    _validate_currency = field_validator("currency")(validate_supported_currency)
    _validate_category = field_validator("category")(validate_user_pickable_income_category)

    # One seat appears at most once. A second line for the same member is two opinions about one
    # person's share, and the DB's UNIQUE would reject it as an opaque integrity error.
    @model_validator(mode="after")
    def validate_distinct_participants(self) -> "SharedIncomeCreate":
        member_ids = [split.member_id for split in self.splits]
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("Each person can appear only once in a split.")
        return self


# Body for PUT /groups/{group_id}/income/{income_id}. A FULL replacement rather than a partial update,
# for the reason the expense mirror is: the amount, the method and the participants are one
# interlocking statement — changing the amount without restating the split would leave exact figures
# that no longer add up to it, and there is no honest way to infer what the user meant.
class SharedIncomeUpdate(SharedIncomeCreate):
    pass


# One member's position in one piece of shared income: what they are entitled to and what reached them.
class SharedIncomeSplitResponse(BaseModel):
    model_config = {"from_attributes": True}

    member_id: int = Field(description="Seat this position belongs to.")
    display_name: str = Field(description="How that person is shown in the group.")
    amount: Decimal = Field(description="What this member is entitled to — their share of the income.")
    received_amount: Decimal = Field(description="What actually reached this member.")
    is_self: bool = Field(description="Whether this is the requesting user's own seat.")


# Response for the shared-income list and for POST / PUT.
#
# `received_by_member_id` / `received_by_display_name` are DERIVED rather than stored, and are null
# whenever the money landed in a SHARED account — the pot's owners received it, in their own
# proportions, and a stored receiver column could not express that, which is why there is not one.
#
# Decided by the DESTINATION rather than by the shape of the splits, for the same reason the expense
# mirror is decided by the funding: a pot with exactly ONE owner has that owner receiving the whole
# amount, which is indistinguishable from one person collecting it — and reporting them as the
# recipient would say somebody took the money personally when it went into the joint account.
class SharedIncomeResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int = Field(description="Shared income id.")
    group_id: int = Field(description="Group that shares it.")
    date: date_type = Field(description="Income date.")
    amount: Decimal = Field(description="Full amount received, before any split.")
    currency: str = Field(description="Currency (ISO 4217).")
    converted_amount: Decimal | None = Field(default=None, description="Full amount in the requested display currency.")
    category: IncomeCategory | None = Field(default=None, description="Income category.")
    notes: str | None = Field(default=None, description="Optional notes.")
    split_method: SplitMethod = Field(description="How the total was divided.")
    destination: IncomeDestination = Field(description="Whether it stayed joint in a pot or was distributed.")
    source_investment_id: int | None = Field(default=None, description="Co-owned asset it came from.")
    source_investment_name: str | None = Field(
        default=None, description="That asset's name; null when it is gone or the caller cannot see the pot holding it."
    )
    paid_to_account_id: int | None = Field(default=None, description="Account the money arrived in.")
    paid_to_account_name: str | None = Field(default=None, description="That account's name, so the row reads without a second request.")
    received_by_member_id: int | None = Field(default=None, description="Seat the money reached; null when it landed in a shared account.")
    received_by_display_name: str | None = Field(default=None, description="That person's name; null when it landed in a shared account.")
    my_share: Decimal | None = Field(default=None, description="The requesting user's own share; null when they take none.")
    splits: list[SharedIncomeSplitResponse] = Field(description="Every member's position in this income.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")
