from datetime import UTC, datetime, timedelta

import bcrypt as _bcrypt
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.repositories import user_repository


# Checks plain password against bcrypt hash.
def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


# Hashes plain password with bcrypt.
def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


# Builds and signs a JWT for the user (sub, email, session_epoch, exp).
def create_access_token(user: User) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "session_epoch": user.session_epoch,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# Fetches user by email from the repository.
async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    return await user_repository.get_by_email(session, email)


# Creates a user with hashed password and persists it.
async def register_user(session: AsyncSession, name: str, email: str, password: str) -> User:
    user = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
    )
    return await user_repository.create(session, user)


# Increments user session_epoch and saves; invalidates all existing JWTs for this user.
async def bump_session_epoch(session: AsyncSession, user: User) -> None:
    user.session_epoch += 1
    user.updated_at = datetime.utcnow()
    await user_repository.save(session, user)
