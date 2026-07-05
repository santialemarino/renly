# Data access for transactions.

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.transaction import Transaction, TransactionType


# Lists transactions for an investment, most recent first (by date desc, then id desc).
async def list_by_investment(
    session: AsyncSession,
    investment_id: int,
) -> list[Transaction]:
    result = await session.execute(
        select(Transaction).where(Transaction.investment_id == investment_id).order_by(Transaction.date.desc(), Transaction.id.desc())
    )
    return list(result.scalars().all())


# Returns dedup-key tuples (investment_id, date, type, amount, quantity) for the user's transactions.
async def list_dedup_keys_by_user(
    session: AsyncSession,
    user_id: int,
) -> list[tuple[int, date_type, TransactionType, Decimal, Decimal | None]]:
    result = await session.execute(
        select(Transaction.investment_id, Transaction.date, Transaction.type, Transaction.amount, Transaction.quantity).where(
            Transaction.user_id == user_id
        )
    )
    return [tuple(row) for row in result.all()]


# Fetches a transaction by id. Returns None if not found.
async def get_by_id(
    session: AsyncSession,
    transaction_id: int,
) -> Transaction | None:
    result = await session.execute(select(Transaction).where(Transaction.id == transaction_id))
    return result.scalar_one_or_none()


# Persists a new transaction and flushes to get the id.
async def create(session: AsyncSession, transaction: Transaction) -> Transaction:
    session.add(transaction)
    await session.flush()
    return transaction


# Bulk-inserts new transactions and flushes to assign ids. Returns the inserted transactions.
async def bulk_create(session: AsyncSession, transactions: list[Transaction]) -> list[Transaction]:
    if not transactions:
        return []
    session.add_all(transactions)
    await session.flush()
    return transactions


# Persists changes to an existing transaction.
async def save(session: AsyncSession, transaction: Transaction) -> None:
    session.add(transaction)


# Deletes a transaction.
async def delete(session: AsyncSession, transaction: Transaction) -> None:
    await session.delete(transaction)


# Namespace to call repository functions (e.g. transaction_repository.list_by_investment).
class TransactionRepository:
    bulk_create = staticmethod(bulk_create)
    create = staticmethod(create)
    delete = staticmethod(delete)
    get_by_id = staticmethod(get_by_id)
    list_by_investment = staticmethod(list_by_investment)
    list_dedup_keys_by_user = staticmethod(list_dedup_keys_by_user)
    save = staticmethod(save)


# Singleton used by services to access transaction persistence.
transaction_repository = TransactionRepository()
