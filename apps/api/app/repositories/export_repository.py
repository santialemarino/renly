# Data access for the full per-user data export (AUTH-6). Gathers every user-owned row across the
# schema in one place so the service can serialize it; keeps the queries in the repository layer.

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
from app.models.income_entry import IncomeEntry
from app.models.installment import Installment
from app.models.investment import Investment
from app.models.investment_collection import InvestmentCollection, InvestmentCollectionMember
from app.models.payment_obligation import PaymentObligation
from app.models.snapshot import InvestmentSnapshot
from app.models.subscription import Subscription
from app.models.transaction import Transaction
from app.models.transfer import Transfer
from app.models.user_settings import UserSettings

# User-owned tables carrying a direct user_id column, keyed by the export name they appear under.
_USER_ID_MODELS = {
    "investments": Investment,
    "investment_snapshots": InvestmentSnapshot,
    "transactions": Transaction,
    "investment_collections": InvestmentCollection,
    "credit_cards": CreditCard,
    "income_entries": IncomeEntry,
    "card_settlements": CardSettlement,
    "subscriptions": Subscription,
    "installments": Installment,
    "expense_entries": ExpenseEntry,
    "card_reconciliations": CardReconciliation,
    "accounts": Account,
    "account_reconciliations": AccountReconciliation,
    "transfers": Transfer,
    "payment_obligations": PaymentObligation,
    "api_keys": ApiKey,
    "user_settings": UserSettings,
}

# Tables the export covers with a query of their own rather than the user_id filter above:
# investment_collection_members joins through its parent investment, and the three group tables are
# not owned by anyone and are scoped by membership.
_MEMBERSHIP_SCOPED_TABLES = frozenset({"investment_collection_members", "groups", "group_members", "group_invites"})

# Every export key dump_user_data() produces. The coverage guard in tests/unit/test_account_lifecycle.py
# reads THIS rather than _USER_ID_MODELS, so a table that needs its own query still has to be declared
# here to pass — and a sibling test asserts dump_user_data's keys match it exactly, so the two cannot
# drift in either direction.
EXPORTED_TABLES = frozenset(model.__tablename__ for model in _USER_ID_MODELS.values()) | _MEMBERSHIP_SCOPED_TABLES


# Returns all of a user's owned rows keyed by export name. Three shapes: the tables with a direct
# user_id column, investment_collection_members (no user_id — joins through the parent investment),
# and the group tables, which are not owned by anyone and are scoped by MEMBERSHIP instead.
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
    return data


# Namespace to call repository functions (e.g. export_repository.dump_user_data).
class ExportRepository:
    dump_user_data = staticmethod(dump_user_data)


# Singleton used by services to gather a user's full data set.
export_repository = ExportRepository()
