# Request/response schemas for expense endpoints.

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.expense_entry import ExpenseCategory
from app.schemas.base import RequestBase, validate_supported_currency


# Body for POST /expenses.
class ExpenseCreate(RequestBase):
    date: date_type = Field(description="Expense date.")
    amount: Decimal = Field(description="Expense amount.", gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(description="Currency (ISO 4217).", max_length=3)
    category: ExpenseCategory | None = Field(default=None, description="Expense category.")
    notes: str | None = Field(default=None, description="Optional notes.", max_length=500)
    payment_method: str | None = Field(default=None, description="Payment method (cash, debit, transfer, credit_card).", max_length=20)
    credit_card_id: int | None = Field(default=None, description="Credit card id (when payment_method = credit_card).")
    source: str = Field(default="manual", description="Entry origin (manual, shortcut, auto, email_parsed).", max_length=20)
    payment_obligation_id: int | None = Field(
        default=None,
        description="When set, links the expense to an obligation and auto-advances next_due_date (Phase 3, Step E).",
    )
    subscription_id: int | None = Field(
        default=None,
        description=(
            "When set, links the expense to a subscription. Mutually exclusive with payment_obligation_id / installment_id (Phase 3, follow-up 3a)."
        ),
    )
    installment_id: int | None = Field(
        default=None,
        description=(
            "When set, links the expense to an installment. Mutually exclusive with payment_obligation_id / subscription_id (Phase 3, follow-up 3a)."
        ),
    )
    cycles_to_advance: int = Field(
        default=1,
        ge=1,
        le=12,
        description=(
            "Number of obligation cycles to pre-pay in one Mark Paid click (Phase 3, follow-up Item 2). "
            "Requires payment_obligation_id set and the obligation must be recurring; raises 400 otherwise. "
            "All N expenses share the same insert date (the request's `date`)."
        ),
    )

    # Entry currencies must be convertible — reject codes outside the supported registry (422).
    _validate_currency = field_validator("currency")(validate_supported_currency)

    # An expense pays at most one commitment-type. Three nullable FKs (payment_obligation_id /
    # subscription_id / installment_id) coexist on the row, but only one may be set on the
    # same insert. The DB allows arbitrary combinations; this validator is the user-facing
    # guardrail at the request boundary. The cycles_to_advance > 1 rule lives here too:
    # multi-cycle Mark Paid only makes sense for a recurring obligation, so sub/installment
    # IDs are forbidden alongside cycles > 1 (the obligation-recurrence check is in the
    # service since it requires a DB lookup).
    @model_validator(mode="after")
    def validate_commitment_link_exclusivity(self) -> "ExpenseCreate":
        link_count = sum(1 for value in (self.payment_obligation_id, self.subscription_id, self.installment_id) if value is not None)
        if link_count > 1:
            raise ValueError("At most one of payment_obligation_id, subscription_id, installment_id may be set.")
        if self.cycles_to_advance > 1 and self.payment_obligation_id is None:
            raise ValueError("cycles_to_advance > 1 requires payment_obligation_id to be set.")
        return self


# Body for PUT /expenses/{id}. Partial update.
# Commitment FKs (payment_obligation_id / subscription_id / installment_id) follow the
# JSON Merge Patch (RFC 7396) convention: omitting the key leaves the link untouched;
# sending `null` explicitly clears it. The router relays only fields the client set via
# `model_dump(exclude_unset=True)`, so the service can distinguish the two intents by
# checking `key in fields` (Phase 3, follow-up Item 10).
class ExpenseUpdate(RequestBase):
    date: date_type | None = Field(default=None, description="Expense date.")
    amount: Decimal | None = Field(default=None, description="Expense amount.", gt=0, max_digits=18, decimal_places=2)
    currency: str | None = Field(default=None, description="Currency (ISO 4217).", max_length=3)
    category: ExpenseCategory | None = Field(default=None, description="Expense category.")
    notes: str | None = Field(default=None, description="Optional notes.", max_length=500)
    payment_method: str | None = Field(default=None, description="Payment method.", max_length=20)
    credit_card_id: int | None = Field(default=None, description="Credit card id.")
    payment_obligation_id: int | None = Field(
        default=None,
        description="Linked payment obligation id. Omit to leave unchanged; send null to clear (Phase 3, follow-up Item 10).",
    )
    subscription_id: int | None = Field(
        default=None,
        description=(
            "Linked subscription id. Omit to leave unchanged; send null to clear. "
            "Mutually exclusive with the other two FKs (Phase 3, follow-up Item 10)."
        ),
    )
    installment_id: int | None = Field(
        default=None,
        description=(
            "Linked installment id. Omit to leave unchanged; send null to clear. "
            "Mutually exclusive with the other two FKs (Phase 3, follow-up Item 10)."
        ),
    )

    # Entry currencies must be convertible — reject codes outside the supported registry (422).
    _validate_currency = field_validator("currency")(validate_supported_currency)

    # Mirrors ExpenseCreate's validator: an expense pays at most one commitment-type.
    # Only validates the fields the client actually set (omitted FKs don't count).
    @model_validator(mode="after")
    def validate_commitment_link_exclusivity(self) -> "ExpenseUpdate":
        provided = self.model_fields_set
        link_count = sum(
            1 for key in ("payment_obligation_id", "subscription_id", "installment_id") if key in provided and getattr(self, key) is not None
        )
        if link_count > 1:
            raise ValueError("At most one of payment_obligation_id, subscription_id, installment_id may be set.")
        return self


# Cursor change emitted by a linked plan on create / update / delete (Phase 3,
# follow-up Item 7). The frontend composes a follow-up toast line — "Netflix's next
# billing date moved to Jun 27, 2026." — branching on plan_type. previous_cursor /
# new_cursor are stringified — ISO date for obligation/subscription, decimal index
# for installment; new_cursor is empty when the plan archived (one-off obligation
# Marked Paid, installment past its final step), previous_cursor is empty when the
# plan re-activated via reverse. total_count is populated for installments only —
# the plan's `installments_count`, so the toast renders "2 of 12 installments paid"
# without a client-side lookup against a potentially-stale active-plans list.
class PlanCursorChange(BaseModel):
    plan_type: str = Field(description="Plan type (obligation, subscription, installment).")
    plan_id: int = Field(description="Plan id.")
    plan_name: str = Field(description="Plan name (for the toast copy).")
    previous_cursor: str = Field(description="Cursor value before the change. Empty when re-activating an archived plan.")
    new_cursor: str = Field(description="Cursor value after the change. Empty when the plan archived.")
    total_count: int | None = Field(
        default=None,
        description=(
            "Total installments for installment plans (None for obligation / subscription). "
            "Lets the toast render 'N of M installments paid' without a client-side lookup."
        ),
    )


# Response for a single expense entry. advance_change / reverse_change carry the cursor
# deltas emitted by the linked-plan symmetric model on POST / PUT — null when nothing
# moved (which is the case for GETs and the list response). Keeping these on the expense
# response itself rather than wrapping preserves the iOS Shortcut's direct field access
# on POST (Phase 3, follow-up Item 7). Update can populate both simultaneously when a FK
# swap fires reverse on the old plan AND advance on the new plan.
class ExpenseResponse(BaseModel):
    id: int = Field(description="Expense id.")
    date: date_type = Field(description="Expense date.")
    amount: Decimal = Field(description="Original expense amount.", max_digits=18, decimal_places=2)
    currency: str = Field(description="Original currency (ISO 4217).")
    converted_amount: Decimal | None = Field(default=None, description="Amount in the requested display currency.", max_digits=18, decimal_places=2)
    category: ExpenseCategory | None = Field(default=None, description="Expense category.")
    notes: str | None = Field(default=None, description="Optional notes.")
    payment_method: str | None = Field(default=None, description="Payment method.")
    credit_card_id: int | None = Field(default=None, description="Credit card id.")
    source: str = Field(description="Entry origin (manual, shortcut, auto, email_parsed).")
    payment_obligation_id: int | None = Field(default=None, description="Linked payment obligation id (Phase 3, Step E).")
    subscription_id: int | None = Field(default=None, description="Linked subscription id (Phase 3, follow-up 3a).")
    installment_id: int | None = Field(default=None, description="Linked installment plan id (Phase 3, follow-up 3a).")
    created_at: datetime = Field(description="Creation timestamp.")
    updated_at: datetime = Field(description="Last update timestamp.")
    advance_change: PlanCursorChange | None = Field(
        default=None,
        description="Cursor advance fired by a linked plan gaining this expense (POST always, PUT on add / swap). Null when nothing advanced.",
    )
    reverse_change: PlanCursorChange | None = Field(
        default=None,
        description="Cursor reverse fired by a linked plan losing this expense (PUT on clear / swap). Null when nothing reversed.",
    )

    model_config = {"from_attributes": True}


# Response for DELETE /expenses/{id} (Phase 3, follow-up Item 10). Carries an optional
# reverse-cursor change when the deleted row was the most-recent linked expense for a
# commitment. Delete never advances — only the reverse_change field is populated.
class ExpenseDeleteResponse(BaseModel):
    reverse_change: PlanCursorChange | None = Field(
        default=None,
        description="Cursor reverse emitted when the deleted row was the most-recent linked expense for a commitment, or null when nothing reversed.",
    )


# Source plan (subscription or installment) referenced by an auto-charge match.
class AutoChargeMatchSourcePlan(BaseModel):
    id: int = Field(description="Source plan id.")
    name: str = Field(description="Source plan name (for display in the dupe-match confirmation dialog).")


# A single auto-charge match — the existing scheduler-generated expense closest to the candidate.
class AutoChargeMatch(BaseModel):
    expense_id: int = Field(description="Existing expense id.")
    date: date_type = Field(description="Existing expense date.")
    source: str = Field(description="Match source: 'subscription' or 'installment'.")
    source_plan: AutoChargeMatchSourcePlan = Field(description="The subscription / installment that owns the auto-charge.")


# Response for GET /expenses/auto-charge-match. match is null when nothing matches the candidate.
class AutoChargeMatchResponse(BaseModel):
    match: AutoChargeMatch | None = Field(default=None, description="The matching auto-generated expense, or null.")


# Response for GET /expenses/cycle-advance-preview (Phase 3, follow-up 3b, revised by Item 9).
# The frontend calls this from the expense form before save: when `would_advance` is False
# the UI surfaces a soft-confirm dialog (e.g. "entry far from next expected cycle; cursor
# will not advance") before continuing with the create. `multi_jump` is True when the
# entry matches a cycle ahead of the current cursor (pre-pay / mis-click) — the link is
# saved, the cursor stays put, and the scheduler back-fills intermediate cycles naturally.
class CycleAdvancePreviewResponse(BaseModel):
    would_advance: bool = Field(description="Whether saving the expense would advance the plan's cursor to the matched cycle's next step.")
    distance_days: int = Field(description="Absolute day distance between the entry date and the closest cycle.")
    next_expected_date: date_type = Field(description="The closest cycle the entry was matched against (informational when would_advance=False).")
    multi_jump: bool = Field(
        default=False, description="True when the matched cycle is ahead of the current cursor by more than one step (pre-pay / mis-click)."
    )


# Paginated response for GET /expenses.
class ExpenseListResponse(BaseModel):
    items: list[ExpenseResponse] = Field(description="Expenses on this page.")
    total: int = Field(description="Total matching expenses.")
    page: int = Field(description="Current page (1-based).")
    page_size: int = Field(description="Items per page.")
    display_currency: str | None = Field(default=None, description="Target currency for converted amounts (None = original).")
    skipped_currencies: list[str] = Field(
        default_factory=list,
        description="Original-currency codes on this page whose converted_amount is null because no exchange rate was stored.",
    )
