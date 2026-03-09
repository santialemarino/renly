from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.transaction import Transaction


# Lists transactions for an investment, most recent first (by date desc, then id desc).
async def list_by_investment(
    session: AsyncSession,
    investment_id: int,
) -> list[Transaction]:
    result = await session.execute(
        select(Transaction)
        .where(Transaction.investment_id == investment_id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
    )
    return list(result.scalars().all())


# Fetches a transaction by id. Returns None if not found.
async def get_by_id(
    session: AsyncSession,
    transaction_id: int,
) -> Transaction | None:
    result = await session.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    return result.scalar_one_or_none()


# Persists transaction, commits, refreshes, and returns it (with id set).
async def create(session: AsyncSession, transaction: Transaction) -> Transaction:
    session.add(transaction)
    await session.commit()
    await session.refresh(transaction)
    return transaction


# Persists changes to an existing transaction.
async def save(session: AsyncSession, transaction: Transaction) -> None:
    session.add(transaction)
    await session.commit()


# Deletes a transaction.
async def delete(session: AsyncSession, transaction: Transaction) -> None:
    await session.delete(transaction)
    await session.commit()


# Namespace to call repository functions (e.g. transaction_repository.list_by_investment).
class TransactionRepository:
    list_by_investment = staticmethod(list_by_investment)
    get_by_id = staticmethod(get_by_id)
    create = staticmethod(create)
    save = staticmethod(save)
    delete = staticmethod(delete)


# Singleton used by services to access transaction persistence.
transaction_repository = TransactionRepository()
