import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt as _bcrypt
import httpx
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain import InvalidTokenError, PasswordBreachedError
from app.models.auth_token import AuthToken, AuthTokenType
from app.models.user import User
from app.models.utils import utcnow
from app.repositories import auth_token_repository, user_repository
from app.services import email_templates
from app.services.email_service import EmailMessage, get_email_service

logger = logging.getLogger(__name__)

# HIBP Pwned Passwords range API (k-anonymity: query by SHA-1 prefix only).
_HIBP_RANGE_URL = "https://api.pwnedpasswords.com/range"

# Token validity windows: verification/email-change links last a day, reset links an hour.
VERIFICATION_TOKEN_TTL = timedelta(hours=24)
EMAIL_CHANGE_TOKEN_TTL = timedelta(hours=24)
RESET_TOKEN_TTL = timedelta(hours=1)

# Web routes the emailed links point at (resolved against settings.web_base_url).
_VERIFY_EMAIL_PATH = "/verify-email"
_RESET_PASSWORD_PATH = "/reset-password"
_LOGIN_PATH = "/login"


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


# Registers an account with a uniform outcome regardless of whether the email already exists
# (AUTH-5): a new address creates an unverified user and emails a verification link; an existing
# one is emailed a "you already have an account" notice. Either way the caller returns the same
# response, so registration never reveals which emails have accounts. The breach check (AUTH-3)
# runs first and is email-independent, so rejecting a breached password leaks nothing.
async def register_account(session: AsyncSession, name: str, email: str, password: str) -> None:
    if await is_password_breached(password):
        raise PasswordBreachedError()

    # Hash up front so both branches below pay the same bcrypt cost. Skipping it on the existing-email
    # path would make that path measurably faster — a response-time oracle revealing which addresses
    # have accounts, which would defeat the uniform-202 anti-enumeration goal (AUTH-5).
    password_hash = hash_password(password)

    existing = await user_repository.get_by_email(session, email)
    if existing is not None:
        await session.commit()
        await _safe_send(email_templates.account_exists_email(existing.email, _login_link()))
        return

    user = User(name=name, email=email, password_hash=password_hash)
    user = await user_repository.create(session, user)
    raw_token = await issue_token(session, user.id, AuthTokenType.email_verification, VERIFICATION_TOKEN_TTL)
    await session.commit()
    await _safe_send(email_templates.verification_email(user.email, _verify_link(raw_token)))


# Increments user session_epoch and saves; invalidates all existing JWTs for this user.
async def bump_session_epoch(session: AsyncSession, user: User) -> None:
    user.session_epoch += 1
    user.updated_at = datetime.now(UTC).replace(tzinfo=None)
    await user_repository.save(session, user)
    await session.commit()


# --- Account-lifecycle tokens (AUTH-1/2/8) ---


# SHA-256 hex of a raw token. The raw value is high-entropy, so a fast hash is sufficient (unlike
# passwords); only the hash is stored, so a DB leak can't reconstruct live links.
def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


# Builds an absolute web link carrying the raw token as a query param.
def _link(path: str, raw_token: str) -> str:
    return f"{settings.web_base_url}{path}?token={raw_token}"


def _verify_link(raw_token: str) -> str:
    return _link(_VERIFY_EMAIL_PATH, raw_token)


def _reset_link(raw_token: str) -> str:
    return _link(_RESET_PASSWORD_PATH, raw_token)


def _login_link() -> str:
    return f"{settings.web_base_url}{_LOGIN_PATH}"


# Sends an email without letting a provider failure surface to the caller — keeps responses uniform
# and never blocks the DB-committed flow on an external outage. The user can re-request the email.
async def _safe_send(message: EmailMessage) -> None:
    try:
        await get_email_service().send(message)
    except Exception:
        logger.warning("Failed to send '%s' email to %s.", message.subject, message.to, exc_info=True)


# Issues a fresh single-use token for the user, invalidating any prior unconsumed token of the same
# type. Stores only the hash and flushes; the caller commits. Returns the raw token for the link.
async def issue_token(
    session: AsyncSession,
    user_id: int,
    token_type: AuthTokenType,
    ttl: timedelta,
    new_email: str | None = None,
) -> str:
    await auth_token_repository.delete_unconsumed_by_user_type(session, user_id, token_type)
    raw_token = secrets.token_urlsafe(32)
    token = AuthToken(
        user_id=user_id,
        token_hash=_hash_token(raw_token),
        token_type=token_type,
        new_email=new_email,
        expires_at=utcnow() + ttl,
    )
    await auth_token_repository.create(session, token)
    return raw_token


# Validates a raw token of the expected type and marks it consumed (flushes; caller commits).
# Raises InvalidTokenError if it is unknown, the wrong type, expired, or already used.
async def consume_token(session: AsyncSession, raw_token: str, token_type: AuthTokenType) -> AuthToken:
    token = await auth_token_repository.get_by_hash(session, _hash_token(raw_token))
    if token is None or token.token_type != token_type or token.consumed_at is not None or token.expires_at < utcnow():
        raise InvalidTokenError()
    token.consumed_at = utcnow()
    await auth_token_repository.save(session, token)
    return token


# --- Email verification (AUTH-1) ---


# (Re)sends a verification email. Uniform no-op when the address has no account or is already
# verified, so it never reveals which emails exist or their verification state.
async def request_verification_email(session: AsyncSession, email: str) -> None:
    user = await user_repository.get_by_email(session, email)
    if user is None or user.email_verified_at is not None:
        return
    raw_token = await issue_token(session, user.id, AuthTokenType.email_verification, VERIFICATION_TOKEN_TTL)
    await session.commit()
    await _safe_send(email_templates.verification_email(user.email, _verify_link(raw_token)))


# Confirms a verification or email-change token (one endpoint serves both, dispatching on the token
# type). Verification marks the address verified; email-change switches the address over (verifying
# the new one) and bumps session_epoch so existing sessions are invalidated. Returns the token type
# so the caller can tailor its response.
async def confirm_email_token(session: AsyncSession, raw_token: str) -> AuthTokenType:
    token = await auth_token_repository.get_by_hash(session, _hash_token(raw_token))
    if token is None or token.consumed_at is not None or token.expires_at < utcnow():
        raise InvalidTokenError()
    if token.token_type not in (AuthTokenType.email_verification, AuthTokenType.email_change):
        raise InvalidTokenError()

    user = await user_repository.get_by_id(session, token.user_id)
    if user is None:
        raise InvalidTokenError()

    if token.token_type == AuthTokenType.email_change:
        # Re-check the target address is still free; a collision since the request must abort.
        clash = await user_repository.get_by_email(session, token.new_email)
        if clash is not None and clash.id != user.id:
            raise InvalidTokenError("That email address is no longer available.")
        user.email = token.new_email
        user.session_epoch += 1

    user.email_verified_at = utcnow()
    token.consumed_at = utcnow()
    await user_repository.save(session, user)
    await auth_token_repository.save(session, token)
    await session.commit()
    return token.token_type


# --- Email change (AUTH-8) ---


# Starts an email-change for an already-authenticated user with a uniform outcome (AUTH-8): a free
# target address is emailed a confirmation link (the switch happens on confirm); an address that
# already belongs to another account is emailed a notice instead, so the response never reveals it.
# Runs on the privileged session because the target-address lookup must see every account (RLS would
# otherwise hide other users' rows). A no-op when the target equals the user's current address.
async def request_email_change(session: AsyncSession, user: User, new_email: str) -> None:
    if new_email == user.email:
        return

    existing = await user_repository.get_by_email(session, new_email)
    if existing is not None and existing.id != user.id:
        await _safe_send(email_templates.email_change_taken_email(new_email, _login_link()))
        return

    raw_token = await issue_token(session, user.id, AuthTokenType.email_change, EMAIL_CHANGE_TOKEN_TTL, new_email=new_email)
    await session.commit()
    await _safe_send(email_templates.email_change_email(new_email, _verify_link(raw_token)))


# --- Password reset (AUTH-2) ---


# Sends a password-reset email. Uniform no-op when the address has no account, so it never reveals
# which emails exist.
async def request_password_reset(session: AsyncSession, email: str) -> None:
    user = await user_repository.get_by_email(session, email)
    if user is None:
        return
    raw_token = await issue_token(session, user.id, AuthTokenType.password_reset, RESET_TOKEN_TTL)
    await session.commit()
    await _safe_send(email_templates.password_reset_email(user.email, _reset_link(raw_token)))


# Resets the password from a valid reset token: rejects breached passwords (AUTH-3), updates the
# hash, and bumps session_epoch so every existing session is killed (AUTH-2).
async def reset_password(session: AsyncSession, raw_token: str, new_password: str) -> None:
    if await is_password_breached(new_password):
        raise PasswordBreachedError()
    token = await consume_token(session, raw_token, AuthTokenType.password_reset)
    user = await user_repository.get_by_id(session, token.user_id)
    if user is None:
        raise InvalidTokenError()
    user.password_hash = hash_password(new_password)
    user.session_epoch += 1
    await user_repository.save(session, user)
    await session.commit()
