# Request/response schemas for a group's shared expenses.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.payment_method import PaymentMethod, ensure_account_pairing, ensure_payment_pairing
from app.models.expense_entry import ExpenseCategory
from app.models.group_money_settings import SplitMethod
from app.schemas.base import RequestBase, validate_supported_currency, validate_user_pickable_expense_category


# One participant's line in a split. `figure` is the figure the chosen method needs and nothing else:
# ignored by `equal`, an amount for `exact`, a weight for `shares`, a percentage for `percentage`. One
# field rather than three, because exactly one is ever meaningful and three would allow a body where
# two are set and neither is authoritative.
class SharedExpenseSplitInput(RequestBase):
    member_id: int = Field(description="Seat taking part in this expense.")
    figure: Decimal | None = Field(default=None, description="Amount, weight or percentage, per the split method.", max_digits=18, decimal_places=2)


# Body for POST /groups/{group_id}/expenses.
#
# `payer_member_id` says WHO fronted the money and the funding fields say HOW. They are separate
# questions: someone can front a bill in cash with no tracked account, and an account can front one
# with no single member behind it.
#
# It is required EXCEPT when the funding account belongs to a pot. Joint money is fronted by that pot's
# owners in their own proportions, so naming one of them as the payer would assert something false, and
# the service refuses a payer alongside a shared account for the same reason.
class SharedExpenseCreate(RequestBase):
    date: date_type = Field(description="Expense date.")
    amount: Decimal = Field(description="Full amount of the expense, before any split.", gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(description="Currency (ISO 4217); also the balance bucket this lands in.", max_length=3)
    category: ExpenseCategory | None = Field(default=None, description="Expense category.")
    notes: str | None = Field(default=None, description="Optional notes.", max_length=500)
    split_method: SplitMethod = Field(description="How the total is divided between the participants.")
    splits: list[SharedExpenseSplitInput] = Field(description="Who takes part, and their figure for the chosen method.", min_length=1)
    payer_member_id: int | None = Field(default=None, description="Seat that fronted the money; omit only when a shared account did.")
    paid_from_account_id: int | None = Field(default=None, description="Account the money left; the payer's own, or one a pot holds.")
    payment_method: PaymentMethod | None = Field(default=None, description="Payment method (cash, debit, transfer, credit_card).")
    credit_card_id: int | None = Field(default=None, description="Card charged (requires payment_method = credit_card).")

    _validate_currency = field_validator("currency")(validate_supported_currency)
    _validate_category = field_validator("category")(validate_user_pickable_expense_category)

    # The same two pairings a private expense enforces: a card id needs the card method, and a card
    # charge never also draws an account (it raises a liability now and draws cash at settlement).
    @model_validator(mode="after")
    def validate_funding_pairing(self) -> "SharedExpenseCreate":
        ensure_payment_pairing(self.payment_method, self.credit_card_id)
        ensure_account_pairing(self.payment_method, self.paid_from_account_id)
        return self

    # One seat appears at most once. A second line for the same member is two opinions about one
    # person's share, and the DB's UNIQUE would reject it as an opaque integrity error.
    @model_validator(mode="after")
    def validate_distinct_participants(self) -> "SharedExpenseCreate":
        member_ids = [split.member_id for split in self.splits]
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("Each person can appear only once in a split.")
        return self


# Body for PUT /groups/{group_id}/expenses/{expense_id}. A FULL replacement rather than a partial
# update, deliberately: the amount, the method and the participants are one interlocking statement —
# changing the amount without restating the split would leave exact figures that no longer add up to
# it, and there is no honest way to infer what the user meant.
class SharedExpenseUpdate(SharedExpenseCreate):
    pass


# One member's position in one shared expense: what they consumed and what they fronted.
class SharedExpenseSplitResponse(BaseModel):
    model_config = {"from_attributes": True}

    member_id: int = Field(description="Seat this position belongs to.")
    display_name: str = Field(description="How that person is shown in the group.")
    amount: Decimal = Field(description="What this member consumed — their share of the expense.")
    paid_amount: Decimal = Field(description="What this member fronted.")
    is_self: bool = Field(description="Whether this is the requesting user's own seat.")


# Response for the shared-expense list and for POST / PUT.
#
# `payer_member_id` / `payer_display_name` are DERIVED rather than stored, and are null whenever a
# SHARED account fronted it — the pot's owners did, in their own proportions, and a stored payer column
# could not express that, which is why there is not one.
#
# Decided by the funding rather than by the shape of the splits, because a pot with exactly ONE owner
# (where a buy-out ends) has that owner fronting the whole amount — indistinguishable from a member
# paying out of their own pocket, and reporting them as the payer would say somebody paid personally
# for money that came out of the joint account.
class SharedExpenseResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int = Field(description="Shared expense id.")
    group_id: int = Field(description="Group that shares it.")
    date: date_type = Field(description="Expense date.")
    amount: Decimal = Field(description="Full amount, before any split.")
    currency: str = Field(description="Currency (ISO 4217).")
    converted_amount: Decimal | None = Field(default=None, description="Full amount in the requested display currency.")
    category: ExpenseCategory | None = Field(default=None, description="Expense category.")
    notes: str | None = Field(default=None, description="Optional notes.")
    split_method: SplitMethod = Field(description="How the total was divided.")
    paid_from_account_id: int | None = Field(default=None, description="Account the money left.")
    paid_from_account_name: str | None = Field(default=None, description="That account's name, so the row reads without a second request.")
    payment_method: str | None = Field(default=None, description="Payment method.")
    credit_card_id: int | None = Field(default=None, description="Card charged.")
    payer_member_id: int | None = Field(default=None, description="Seat that fronted it; null when a shared account did.")
    payer_display_name: str | None = Field(default=None, description="That person's name; null when a shared account fronted it.")
    my_share: Decimal | None = Field(default=None, description="The requesting user's own share; null when they took no part.")
    splits: list[SharedExpenseSplitResponse] = Field(description="Every member's position in this expense.")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")
