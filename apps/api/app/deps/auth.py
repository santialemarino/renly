from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings
from app.deps.db import SessionDep
from app.models.user import User

bearer = HTTPBearer()


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)],
) -> User:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        user_id: int | None = payload.get("sub")
        token_epoch: int | None = payload.get("session_epoch")
        if user_id is None or token_epoch is None:
            raise invalid
    except JWTError:
        raise invalid

    user = await session.get(User, user_id)
    if user is None:
        raise invalid

    # Invalidate tokens issued before the last session revocation
    if user.session_epoch != token_epoch:
        raise invalid

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
