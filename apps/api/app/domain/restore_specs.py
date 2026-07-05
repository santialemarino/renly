# Per-entity restore specs for the JSON round-trip (re-importing a Renly export). Each spec tells the
# generic restore engine how to rebuild one entity: its model, which foreign keys to remap to freshly
# inserted parents, and which fields to force-null.
#
# Design (non-destructive, additive):
#   - Rows insert in list order (parents before children); a child's FK is remapped from the exported
#     (old) parent id to the freshly inserted id via the export's unique ids.
#   - Every row is inserted — restore never content-dedups, which would wrongly drop legitimately-distinct
#     rows (two same-priced coffees, two investments both named "Cash"). Because parents are always
#     re-created with fresh ids, restored children attach only to those new parents and can never collide
#     with the target's existing rows on a unique constraint (snapshots' UNIQUE(investment_id, date), the
#     group-members composite PK). Restore is therefore additive but NOT idempotent: re-restoring the same
#     file adds everything again, so restore into a fresh account (see docs/public/api-reference.md).
#   - The circular reconciliation/settlement cluster (card_reconciliations ↔ expense/income) and
#     preference/secret rows are out of scope; see SKIPPED_ENTITIES. Expense/income reconciliation and
#     scheduler links are nulled so restored rows are plain historical entries with no dangling FK and
#     no risk of tripping the scheduler's partial-unique (subscription_id, date)/(installment_id, date).

from dataclasses import dataclass

from sqlmodel import SQLModel

from app.models.credit_card import CreditCard
from app.models.expense_entry import ExpenseEntry
from app.models.income_entry import IncomeEntry
from app.models.installment import Installment
from app.models.investment import Investment
from app.models.investment_group import InvestmentGroup, InvestmentGroupMember
from app.models.payment_obligation import PaymentObligation
from app.models.snapshot import InvestmentSnapshot
from app.models.subscription import Subscription
from app.models.transaction import Transaction

# Exported sections the restore flow deliberately does not write, reported to the user for transparency.
# api_keys carry no secret (unusable); user_settings is a single preferences row (skipped to avoid
# overwriting the target's settings); card_settlements/card_reconciliations are the circular-FK cluster.
SKIPPED_ENTITIES = ("api_keys", "user_settings", "card_settlements", "card_reconciliations")


# A foreign key on the model that points at another restored entity and must be remapped to the new id.
@dataclass(frozen=True)
class FkRef:
    field: str
    parent: str  # export key of the parent entity
    required: bool  # a required FK that can't be resolved makes the row unresolved (skipped)


# How to restore one entity: its model, foreign keys to remap, and fields to force-null on restore.
@dataclass(frozen=True)
class RestoreSpec:
    key: str  # export key, e.g. "investments"
    model: type[SQLModel]
    fks: tuple[FkRef, ...] = ()
    null_fields: tuple[str, ...] = ()
    has_user_id: bool = True  # investment_group_members is keyed via its parents, not a user_id column
    has_id: bool = True  # investment_group_members has a composite PK, no surrogate id to remap


# Restore order matters: parents precede children so FK remaps resolve. Independent entities first.
RESTORE_SPECS: tuple[RestoreSpec, ...] = (
    RestoreSpec("investments", Investment),
    RestoreSpec("investment_groups", InvestmentGroup),
    RestoreSpec("credit_cards", CreditCard),
    RestoreSpec(
        "investment_group_members",
        InvestmentGroupMember,
        fks=(FkRef("investment_id", "investments", True), FkRef("group_id", "investment_groups", True)),
        has_user_id=False,
        has_id=False,
    ),
    RestoreSpec(
        "investment_snapshots",
        InvestmentSnapshot,
        fks=(FkRef("investment_id", "investments", True),),
    ),
    RestoreSpec(
        "transactions",
        Transaction,
        fks=(FkRef("investment_id", "investments", True),),
    ),
    RestoreSpec(
        "subscriptions",
        Subscription,
        fks=(FkRef("credit_card_id", "credit_cards", False),),
    ),
    RestoreSpec(
        "installments",
        Installment,
        fks=(FkRef("credit_card_id", "credit_cards", False),),
    ),
    RestoreSpec(
        "payment_obligations",
        PaymentObligation,
        fks=(FkRef("credit_card_id", "credit_cards", False),),
    ),
    RestoreSpec(
        "expense_entries",
        ExpenseEntry,
        fks=(FkRef("credit_card_id", "credit_cards", False), FkRef("payment_obligation_id", "payment_obligations", False)),
        null_fields=("subscription_id", "installment_id", "reconciliation_id"),
    ),
    RestoreSpec(
        "income_entries",
        IncomeEntry,
        null_fields=("reconciliation_id",),
    ),
)
