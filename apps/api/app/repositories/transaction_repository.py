# Data access for transactions.

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.transaction import Transaction


# Lists transactions for an investment, most recent first (by date desc, then id desc).
async def list_by_investment(
    session: AsyncSession,
    investment_id: int,
) -> list[Transaction]:
    result = await session.execute(
        select(Transaction).where(Transaction.investment_id == investment_id).order_by(Transaction.date.desc(), Transaction.id.desc())
    )
    return list(result.scalars().all())


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


# Persists changes to an existing transaction.
async def save(session: AsyncSession, transaction: Transaction) -> None:
    session.add(transaction)


# Deletes a transaction.
async def delete(session: AsyncSession, transaction: Transaction) -> None:
    await session.delete(transaction)


# Namespace to call repository functions (e.g. transaction_repository.list_by_investment).
class TransactionRepository:
    create = staticmethod(create)
    delete = staticmethod(delete)
    get_by_id = staticmethod(get_by_id)
    list_by_investment = staticmethod(list_by_investment)
    save = staticmethod(save)


# Singleton used by services to access transaction persistence.
transaction_repository = TransactionRepository()
