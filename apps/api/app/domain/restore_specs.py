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
#   - The circular reconciliation cluster (card_reconciliations and account_reconciliations, both ↔
#     expense/income) and preference/secret rows are out of scope; see SKIPPED_ENTITIES.
#     Expense/income reconciliation and scheduler links are nulled so restored rows are plain historical
#     entries with no dangling FK and no risk of tripping the scheduler's partial-unique
#     (subscription_id, date)/(installment_id, date).
#   - accounts ARE restored, and entry → account links survive via an account_id remap. A cash balance
#     is derived from opening_balance plus its linked rows, so nulling the link (what this engine did
#     before accounts were exported) silently zeroed a restored user's cash until they re-created every
#     account and reconciled it. Restoring the parent first and remapping the child's id keeps the
#     balance correct with no user action.
#   - account_reconciliations stay skipped even though accounts are now restorable, and that is
#     deliberate rather than an oversight: a reconciliation is a point-in-time true-up recorded against
#     a balance the restore has just re-derived from scratch, so replaying an old one would post a
#     second adjustment for drift that no longer exists. Reconcile after restoring.
#   - card_settlements ARE restored, and were never actually part of the circular cluster an older
#     comment here filed them under: nothing references them, and their FKs (credit_cards, users,
#     accounts) all resolve. Skipping them left a restored card showing its charges with none of the
#     payments against them, so its balance — sum(expenses) - sum(settlements) — came back at full
#     historical debt and understated net worth by every payment the user had ever made.

from dataclasses import dataclass

from sqlmodel import SQLModel

from app.models.account import Account
from app.models.card_settlement import CardSettlement
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
from app.models.transfer import Transfer

# Exported sections the restore flow deliberately does not write, reported to the user for transparency.
# api_keys carry no secret (unusable); user_settings is a single preferences row (skipped to avoid
# overwriting the target's settings); the two reconciliation tables are the circular-FK cluster, and
# replaying an old true-up against a freshly re-derived balance would be wrong regardless (see above).
SKIPPED_ENTITIES = ("api_keys", "user_settings", "card_reconciliations", "account_reconciliations")


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
    RestoreSpec("accounts", Account),
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
        fks=(
            FkRef("credit_card_id", "credit_cards", False),
            FkRef("payment_obligation_id", "payment_obligations", False),
            FkRef("account_id", "accounts", False),
        ),
        null_fields=("subscription_id", "installment_id", "reconciliation_id", "account_reconciliation_id"),
    ),
    RestoreSpec(
        "income_entries",
        IncomeEntry,
        fks=(FkRef("account_id", "accounts", False),),
        null_fields=("reconciliation_id", "account_reconciliation_id"),
    ),
    # The card FK is required (NOT NULL, and a settlement means nothing without the card it paid);
    # the funding account is optional and nulls out like any other unresolved optional link.
    RestoreSpec(
        "card_settlements",
        CardSettlement,
        fks=(FkRef("credit_card_id", "credit_cards", True), FkRef("account_id", "accounts", False)),
    ),
    # Both legs are NOT NULL and required: a transfer whose accounts can't both be resolved is dropped
    # rather than half-restored, because the balance union sums each leg independently — one surviving
    # leg would move money out of an account and into nowhere.
    RestoreSpec(
        "transfers",
        Transfer,
        fks=(FkRef("from_account_id", "accounts", True), FkRef("to_account_id", "accounts", True)),
    ),
)
