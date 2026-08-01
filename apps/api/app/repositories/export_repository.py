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
from app.models.income_entry import IncomeEntry
from app.models.installment import Installment
from app.models.investment import Investment
from app.models.investment_group import InvestmentGroup, InvestmentGroupMember
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
    "investment_groups": InvestmentGroup,
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


# Returns all of a user's owned rows keyed by export name. investment_group_members has no user_id,
# so it joins through the parent investment; the rest filter on their direct user_id column.
async def dump_user_data(session: AsyncSession, user_id: int) -> dict[str, list]:
    data: dict[str, list] = {}
    for name, model in _USER_ID_MODELS.items():
        result = await session.execute(select(model).where(model.user_id == user_id))
        data[name] = list(result.scalars().all())

    members = await session.execute(
        select(InvestmentGroupMember).join(Investment, Investment.id == InvestmentGroupMember.investment_id).where(Investment.user_id == user_id)
    )
    data["investment_group_members"] = list(members.scalars().all())
    return data


# Namespace to call repository functions (e.g. export_repository.dump_user_data).
class ExportRepository:
    dump_user_data = staticmethod(dump_user_data)


# Singleton used by services to gather a user's full data set.
export_repository = ExportRepository()
