from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.auth import LoginRequest, MeResponse, RegisterRequest, TokenResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


# Creates a new user and returns a JWT. Returns 409 if email already registered.
@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: SessionDep) -> TokenResponse:
    user = await auth_service.get_user_by_email(session, body.email)
    if user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = await auth_service.register_user(session, body.name, body.email, body.password)
    token = auth_service.create_access_token(user)
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


# Authenticates by email/password and returns a JWT. Returns 401 if invalid.
@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: SessionDep) -> TokenResponse:
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
    )
