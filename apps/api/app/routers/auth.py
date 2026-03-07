from datetime import UTC, datetime, timedelta

import bcrypt as _bcrypt
from fastapi import APIRouter, HTTPException, status
from jose import jwt
from pydantic import BaseModel
from sqlmodel import select

from app.config import settings
from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


def _verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def _hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MeResponse(BaseModel):
    uid: int
    email: str
    name: str


def _create_access_token(user: User) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "session_epoch": user.session_epoch,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: SessionDep) -> TokenResponse:
    result = await session.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        name=body.name,
        email=body.email,
        password_hash=_hash_password(body.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    token = _create_access_token(user)
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: SessionDep) -> TokenResponse:
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not _verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = _create_access_token(user)
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(current_user: CurrentUser, session: SessionDep) -> None:
    """Invalidate all existing tokens by bumping session_epoch."""
    current_user.session_epoch += 1
    current_user.updated_at = datetime.now(UTC)
    session.add(current_user)
    await session.commit()


@router.get("/me", response_model=MeResponse)
async def me(current_user: CurrentUser) -> MeResponse:
    return MeResponse(
        uid=current_user.id,
        email=current_user.email,
        name=current_user.name,
    )
