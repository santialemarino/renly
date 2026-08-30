# Data access for the full per-user data export (AUTH-6). Gathers every user-owned row across the
# schema in one place so the service can serialize it; keeps the queries in the repository layer.

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.account import Account
from app.models.account_reconciliation import AccountReconciliation
from app.models.api_key import ApiKey
from app.models.card_reconciliation import CardReconciliation
from app.models.card_settlement import CardSettlement
from app.models.credit_card import CreditCard
from app.models.expense_entry import ExpenseEntry
from app.models.group import Group, GroupMember
from app.models.group_invite import GroupInvite
from app.models.group_money_settings import GroupMoneySettings
from app.models.group_settlement import GroupSettlement
from app.models.income_entry import IncomeEntry
from app.models.installment import Installment
from app.models.investment import Investment
from app.models.investment_collection import InvestmentCollection, InvestmentCollectionMember
from app.models.payment_obligation import PaymentObligation
from app.models.pot import Pot, PotMemberPermission, PotOwnershipEvent
from app.models.shared_expense import SharedExpense, SharedExpenseSplit
from app.models.snapshot import InvestmentSnapshot
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.models.transfer import Transfer
from app.models.user_settings import UserSettings

# Tables whose user_id is now an OWNER rather than an author, so a co-owned row carries user_id NULL
# and the plain owner filter below cannot see it. Each is exported by a SCOPE query instead: the
# user's own rows, plus the rows of every pot they may see.
# This list is not a convenience — without it, `select(model).where(model.user_id == user_id)` would
# silently omit every shared holding from a user's data export with no error at all, which is the one
# failure mode an export must never have.
_SCOPED_MODELS = {
    "investments": Investment,
    "investment_snapshots": InvestmentSnapshot,
    "transactions": Transaction,
    "accounts": Account,
    "account_reconciliations": AccountReconciliation,
    "transfers": Transfer,
}

# User-owned tables carrying a direct user_id column, keyed by the export name they appear under.
_USER_ID_MODELS = {
    "investment_collections": InvestmentCollection,
    "credit_cards": CreditCard,
    "income_entries": IncomeEntry,
    "card_settlements": CardSettlement,
    "subscriptions": Subscription,
    "installments": Installment,
    "expense_entries": ExpenseEntry,
    "card_reconciliations": CardReconciliation,
    "payment_obligations": PaymentObligation,
    "api_keys": ApiKey,
    "user_settings": UserSettings,
}

# Tables the export covers with a query of their own rather than the user_id filter above:
# investment_collection_members joins through its parent investment, and the three group tables are
# not owned by anyone and are scoped by membership.
_MEMBERSHIP_SCOPED_TABLES = frozenset(
    {
        "investment_collection_members",
        "groups",
        "group_members",
        "group_invites",
        "group_money_settings",
        "pots",
        "pot_member_permissions",
        "pot_ownership_events",
        "shared_expenses",
        "shared_expense_splits",
        "group_settlements",
    }
)

# Every export key dump_user_data() produces. The coverage guard in tests/unit/test_account_lifecycle.py
# reads THIS rather than _USER_ID_MODELS, so a table that needs its own query still has to be declared
# here to pass — and a sibling test asserts dump_user_data's keys match it exactly, so the two cannot
# drift in either direction.
EXPORTED_TABLES = (
    frozenset(model.__tablename__ for model in _USER_ID_MODELS.values())
    | frozenset(model.__tablename__ for model in _SCOPED_MODELS.values())
    | _MEMBERSHIP_SCOPED_TABLES
)


# Returns all of a user's rows keyed by export name. Four shapes now:
#   * tables with a direct user_id column (a plain owner filter);
#   * the SCOPED stock tables, where user_id means owner and is NULL for a co-owned row — those need
#     the pot branch as well, or every shared holding would vanish from the export with no error;
#   * investment_collection_members (no user_id — joins through the parent investment);
#   * the group and pot tables, which are owned by nobody and are scoped by MEMBERSHIP instead.
#
# The group tables are exported but deliberately NOT restorable (they are absent from RESTORE_SPECS).
# The asymmetry is the correct one: an export answers "what does Renly hold about me", and a group I
# belong to is part of that answer. A restore cannot recreate a shared group from one member's file —
# it would stand every other member up as a placeholder bearing a real person's name, in a group none
# of them is actually in. Exporting a true record and refusing a false restore is the honest pair.
async def dump_user_data(session: AsyncSession, user_id: int) -> dict[str, list]:
    data: dict[str, list] = {}
    for name, model in _USER_ID_MODELS.items():
        result = await session.execute(select(model).where(model.user_id == user_id))
        data[name] = list(result.scalars().all())

    # Pots the user may see, resolved once and reused: an export is a snapshot of one moment, so
    # asking the question per table would also risk two tables disagreeing about what was visible.
    visible_pot_ids_stmt = select(Pot.id)
    visible_pot_ids = list((await session.execute(visible_pot_ids_stmt)).scalars().all())
    for name, model in _SCOPED_MODELS.items():
        result = await session.execute(select(model).where(or_(model.user_id == user_id, model.pot_id.in_(visible_pot_ids))))
        data[name] = list(result.scalars().all())

    members = await session.execute(
        select(InvestmentCollectionMember)
        .join(Investment, Investment.id == InvestmentCollectionMember.investment_id)
        .where(Investment.user_id == user_id)
    )
    data["investment_collection_members"] = list(members.scalars().all())

    # Every group the user holds an ACTIVE seat in — the same set the app shows them, so the export
    # cannot disclose a group they can no longer see. A former member's own historical seat is not
    # included, matching what the membership policies allow them to read.
    group_ids_stmt = select(GroupMember.group_id).where(GroupMember.user_id == user_id, GroupMember.is_active)
    groups = await session.execute(select(Group).where(Group.id.in_(group_ids_stmt)))
    data["groups"] = list(groups.scalars().all())
    # The full roster and the outstanding invites of those groups, which is what the user sees in-app.
    group_members = await session.execute(select(GroupMember).where(GroupMember.group_id.in_(group_ids_stmt)))
    data["group_members"] = list(group_members.scalars().all())
    group_invites = await session.execute(select(GroupInvite).where(GroupInvite.group_id.in_(group_ids_stmt)))
    data["group_invites"] = list(group_invites.scalars().all())
    # The flow half of those groups: what they spent together, how each expense divided, and every
    # settlement recorded against the resulting balances. Exported for the same reason the rest of the
    # group is — a shared expense you took part in is part of what Renly holds about you — and NOT
    # restorable for the same reason either: rebuilding a group's ledger from one member's file would
    # stand every other member up as a placeholder bearing a real person's name and owing real money.
    money_settings = await session.execute(select(GroupMoneySettings).where(GroupMoneySettings.group_id.in_(group_ids_stmt)))
    data["group_money_settings"] = list(money_settings.scalars().all())
    shared_expenses = await session.execute(select(SharedExpense).where(SharedExpense.group_id.in_(group_ids_stmt)))
    data["shared_expenses"] = list(shared_expenses.scalars().all())
    shared_splits = await session.execute(select(SharedExpenseSplit).where(SharedExpenseSplit.group_id.in_(group_ids_stmt)))
    data["shared_expense_splits"] = list(shared_splits.scalars().all())
    settlements = await session.execute(select(GroupSettlement).where(GroupSettlement.group_id.in_(group_ids_stmt)))
    data["group_settlements"] = list(settlements.scalars().all())

    # The pots the user may see, with their permissions and full ownership ledger. Exported for the
    # same reason the group tables are — a portfolio you co-own is part of what Renly holds about you
    # — and NOT restorable for the same reason either: rebuilding a shared pot from one member's file
    # would issue units to placeholders standing in for real people who are in no such pot.
    pots = await session.execute(select(Pot).where(Pot.id.in_(visible_pot_ids)))
    data["pots"] = list(pots.scalars().all())
    permissions = await session.execute(select(PotMemberPermission).where(PotMemberPermission.pot_id.in_(visible_pot_ids)))
    data["pot_member_permissions"] = list(permissions.scalars().all())
    events = await session.execute(select(PotOwnershipEvent).where(PotOwnershipEvent.pot_id.in_(visible_pot_ids)))
    data["pot_ownership_events"] = list(events.scalars().all())
    return data


# Namespace to call repository functions (e.g. export_repository.dump_user_data).
class ExportRepository:
    dump_user_data = staticmethod(dump_user_data)


# Singleton used by services to gather a user's full data set.
export_repository = ExportRepository()
