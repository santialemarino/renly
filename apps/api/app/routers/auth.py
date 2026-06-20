from fastapi import APIRouter, HTTPException, Request, Response, status

from app.config import settings
from app.deps.auth import CurrentUser
from app.deps.db import AdminSessionDep, SessionDep
from app.rate_limit import LOGIN_LIMIT, REGISTER_LIMIT, limiter
from app.schemas.auth import LoginRequest, MeResponse, RegisterRequest, TokenResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


# Creates a new user and returns a JWT.
# Anti-enumeration (AUTH-5, M1 part): a duplicate email returns a generic 400 — the same response
# as any other rejected registration — instead of a 409 that confirms the address has an account.
# The full always-uniform response + "you already have an account" email lands in M2 (SHELL-3).
# Uses the privileged session: there is no user context yet, and the new row's id can't satisfy
# the users RLS policy, so the insert + email lookup run as the owner (bypasses RLS) (SEC-15).
# The unused `response` param is required by the rate limiter: with headers_enabled it injects
# X-RateLimit-* into a Response, and without one a successful (model-returning) request 500s.
@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(REGISTER_LIMIT)
async def register(request: Request, response: Response, body: RegisterRequest, session: AdminSessionDep) -> TokenResponse:
    existing = await auth_service.get_user_by_email(session, body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration could not be completed.",
        )

    user = await auth_service.register_user(session, body.name, body.email, body.password)
    token = auth_service.create_access_token(user)
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


# Authenticates by email/password and returns a JWT. Returns 401 if invalid.
# Uses the privileged session: the by-email lookup is pre-auth (no user context), so it bypasses
# the users RLS policy (SEC-15).
@router.post("/login", response_model=TokenResponse)
@limiter.limit(LOGIN_LIMIT)
async def login(request: Request, response: Response, body: LoginRequest, session: AdminSessionDep) -> TokenResponse:
    user = await auth_service.get_user_by_email(session, body.email)
    if not user or not auth_service.verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_service.create_access_token(user)
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


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
    )
