# Dual authentication dependency: accepts JWT (web) or API key (iOS Shortcut).
# Use JwtOrApiKeyUser instead of CurrentUser on endpoints that support both.

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.deps.db import SessionDep
from app.models.user import User
from app.services import api_key_service

bearer_optional = HTTPBearer(auto_error=False)


# Try JWT first, fall back to API key verification.
async def get_jwt_or_api_key_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_optional)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    token = credentials.credentials

    # Try JWT first.
    from jose import JWTError, jwt

    from app.config import settings

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        raw_sub = payload.get("sub")
        user_id: int | None = int(raw_sub) if raw_sub is not None else None
        token_epoch: int | None = payload.get("session_epoch")
        if user_id is not None and token_epoch is not None:
            user = await session.get(User, user_id)
            if user is not None and user.session_epoch == token_epoch:
                return user
    except (JWTError, ValueError):
        pass

    # Fall back to API key.
    user = await api_key_service.verify_api_key(session, token)
    if user is not None:
        return user

    raise unauthorized


JwtOrApiKeyUser = Annotated[User, Depends(get_jwt_or_api_key_user)]
