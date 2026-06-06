import hashlib
import logging
from datetime import UTC, datetime, timedelta

import bcrypt as _bcrypt
import httpx
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain import PasswordBreachedError
from app.models.user import User
from app.repositories import user_repository

logger = logging.getLogger(__name__)

# HIBP Pwned Passwords range API (k-anonymity: query by SHA-1 prefix only).
_HIBP_RANGE_URL = "https://api.pwnedpasswords.com/range"


# Checks plain password against bcrypt hash.
def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


# Hashes plain password with bcrypt (gensalt defaults to cost 12).
def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


# Checks a password against the HIBP Pwned Passwords range API using k-anonymity:
# SHA-1 the password, send only the first 5 hex chars, then match the suffix locally.
# Returns True if the password appears in a known breach. Fails open (returns False)
# when HIBP is unreachable so an external outage never blocks signup.
async def is_password_breached(plain: str) -> bool:
    digest = hashlib.sha1(plain.encode()).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{_HIBP_RANGE_URL}/{prefix}")
            response.raise_for_status()
            body = response.text
    except httpx.HTTPError:
        logger.warning("HIBP unreachable; allowing signup (fail-open).")
        return False

    return any(line.split(":", 1)[0].strip().upper() == suffix for line in body.splitlines())


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
# Blocks registration when the password appears in a known breach (HIBP).
async def register_user(session: AsyncSession, name: str, email: str, password: str) -> User:
    if await is_password_breached(password):
        raise PasswordBreachedError()
    user = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
    )
    user = await user_repository.create(session, user)
    await session.commit()
    return user


# Increments user session_epoch and saves; invalidates all existing JWTs for this user.
async def bump_session_epoch(session: AsyncSession, user: User) -> None:
    user.session_epoch += 1
    user.updated_at = datetime.now(UTC).replace(tzinfo=None)
    await user_repository.save(session, user)
    await session.commit()
