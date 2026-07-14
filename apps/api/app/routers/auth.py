from fastapi import APIRouter, HTTPException, Request, Response, status

from app.config import SignupMode, settings
from app.deps.auth import CurrentUser
from app.deps.db import AdminSessionDep, SessionDep
from app.domain import EmailNotVerifiedError
from app.models.auth_token import AuthTokenType
from app.models.user import User
from app.rate_limit import (
    FORGOT_PASSWORD_LIMIT,
    LOGIN_LIMIT,
    REGISTER_LIMIT,
    RESET_PASSWORD_LIMIT,
    VERIFY_EMAIL_LIMIT,
    limiter,
)
from app.schemas.auth import (
    ConfirmEmailRequest,
    ConfirmEmailResponse,
    EmailActionRequest,
    LoginRequest,
    MeResponse,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SignupContextResponse,
    TokenResponse,
)
from app.services import auth_service, invite_service, refresh_token_service

router = APIRouter(prefix="/auth", tags=["auth"])

# Uniform acknowledgement for the anti-enumeration flows (register / verify-request / forgot): the
# same message whether or not the address has an account, so existence is never revealed.
_UNIFORM_ACK = "If that email address can be used, you'll receive a message with next steps."

# NOTE: every @limiter.limit endpoint must declare a `response: Response` parameter. With
# headers_enabled, slowapi injects the X-RateLimit-* headers into that Response on the success path;
# without it slowapi raises (the success path returns a Pydantic model, not a Response).


# Builds the login/refresh payload: a fresh access token for the user plus the issued refresh token.
def _token_response(user: User, issued: refresh_token_service.IssuedRefreshToken) -> TokenResponse:
    return TokenResponse(
        access_token=auth_service.create_access_token(user),
        expires_in=settings.jwt_expire_minutes * 60,
        refresh_token=issued.raw_token,
        refresh_expires_in=issued.expires_in,
    )


# Registers an account. Anti-enumeration (AUTH-5): always returns the same uniform 202 — a new
# address is emailed a verification link, an existing one a "you already have an account" notice —
# so the response never reveals which emails are registered. Runs on the privileged session (no
# user context yet; the insert + email lookup must bypass the users RLS policy — SEC-15).
@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(REGISTER_LIMIT)
async def register(request: Request, response: Response, body: RegisterRequest, session: AdminSessionDep) -> MessageResponse:
    await auth_service.register_account(session, body.name, body.email, body.password, body.invite_token)
    return MessageResponse(detail=_UNIFORM_ACK)


# Tells the web whether signup is invite-only and, for a valid invite token, the address to lock the
# form to (so the signup page shows the invite-only screen vs the form). Privileged session: the
# invite lookup is pre-auth (no user context), so it bypasses RLS (SEC-15).
@router.get("/signup-context", response_model=SignupContextResponse)
async def signup_context(session: AdminSessionDep, invite: str | None = None) -> SignupContextResponse:
    invited_email = None
    if settings.signup_mode == SignupMode.invite and invite:
        found = await invite_service.get_pending_invite_by_token(session, invite)
        invited_email = found.email if found else None
    return SignupContextResponse(signup_mode=settings.signup_mode, invited_email=invited_email)


# Authenticates by email/password and returns a JWT. Returns 401 if invalid, 403 if the email is
# not yet verified (AUTH-1). Uses the privileged session: the by-email lookup is pre-auth (no user
# context), so it bypasses the users RLS policy (SEC-15).
@router.post("/login", response_model=TokenResponse)
@limiter.limit(LOGIN_LIMIT)
async def login(request: Request, response: Response, body: LoginRequest, session: AdminSessionDep) -> TokenResponse:
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = await auth_service.get_user_by_email(session, body.email)
    # Release the admin-pool connection before the ~250ms threaded bcrypt: login/register/API-key
    # verification share the small admin pool, and holding a connection across the hash would let an
    # auth burst exhaust it and queue on pool_timeout. The by-email read is done; commit() returns
    # the connection now and issue_refresh_token below re-acquires one for the write.
    # expire_on_commit=False keeps `user` usable without a reload.
    await session.commit()
    if user is None:
        # Timing equalization (AUTH-5): burn the same bcrypt cost as a real verify so an unknown
        # email is indistinguishable from a wrong password by response time.
        await auth_service.verify_password(body.password, auth_service.DUMMY_PASSWORD_HASH)
        raise invalid_credentials
    if not await auth_service.verify_password(body.password, user.password_hash):
        raise invalid_credentials
    if user.email_verified_at is None:
        raise EmailNotVerifiedError()

    issued = await refresh_token_service.issue_refresh_token(session, user, body.remember_me)
    return _token_response(user, issued)


# Exchanges a valid refresh token for a new access token and rotates the refresh token (AUTH-7).
# Returns 401 if the refresh token is unknown, expired, revoked, reused, or predates a session_epoch
# bump (logout / password change). Privileged session: the call is pre-auth (it carries a refresh
# token, not an access token), so the lookup bypasses RLS (SEC-15).
@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, session: AdminSessionDep) -> TokenResponse:
    user, issued = await refresh_token_service.rotate_refresh_token(session, body.refresh_token)
    return _token_response(user, issued)


# (Re)sends an email-verification link (AUTH-1). Uniform 202 regardless of whether the address has
# an unverified account. Privileged session (pre-auth lookup bypasses RLS — SEC-15).
@router.post("/verify-email/request", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(VERIFY_EMAIL_LIMIT)
async def request_verification(request: Request, response: Response, body: EmailActionRequest, session: AdminSessionDep) -> MessageResponse:
    await auth_service.request_verification_email(session, body.email)
    return MessageResponse(detail=_UNIFORM_ACK)


# Confirms an email-verification or email-change token (AUTH-1/8); one endpoint serves both,
# dispatching on the token type. Returns which flow completed. Privileged session (pre-auth — the
# user may not be logged in when clicking the link; bypasses RLS — SEC-15).
@router.post("/verify-email/confirm", response_model=ConfirmEmailResponse)
async def confirm_verification(body: ConfirmEmailRequest, session: AdminSessionDep) -> ConfirmEmailResponse:
    token_type = await auth_service.confirm_email_token(session, body.token)
    detail = (
        "Your new email address is confirmed." if token_type == AuthTokenType.email_change else "Your email address is verified. You can now log in."
    )
    return ConfirmEmailResponse(detail=detail, token_type=token_type)


# Sends a password-reset link (AUTH-2). Uniform 202 regardless of whether the address has an
# account. Privileged session (pre-auth lookup bypasses RLS — SEC-15).
@router.post("/forgot-password", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(FORGOT_PASSWORD_LIMIT)
async def forgot_password(request: Request, response: Response, body: EmailActionRequest, session: AdminSessionDep) -> MessageResponse:
    await auth_service.request_password_reset(session, body.email)
    return MessageResponse(detail=_UNIFORM_ACK)


# Resets the password from a valid reset token and kills existing sessions (AUTH-2). Returns 400 if
# the token is invalid/expired/used or the new password is breached. Privileged session (pre-auth).
@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit(RESET_PASSWORD_LIMIT)
async def reset_password(request: Request, response: Response, body: ResetPasswordRequest, session: AdminSessionDep) -> MessageResponse:
    await auth_service.reset_password(session, body.token, body.password)
    return MessageResponse(detail="Your password has been reset. You can now log in.")


# Invalidates all existing JWTs for the current user by bumping session_epoch.
@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(current_user: CurrentUser, session: SessionDep) -> None:
    await auth_service.bump_session_epoch(session, current_user)


# Returns the current authenticated user.
@router.get("/me", response_model=MeResponse)
async def me(current_user: CurrentUser) -> MeResponse:
    return MeResponse(
        uid=current_user.id,
        email=current_user.email,
        name=current_user.name,
        plan=current_user.plan,
        email_verified=current_user.email_verified_at is not None,
        is_admin=current_user.is_admin,
    )
