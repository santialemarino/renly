from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings
from app.db import set_session_user
from app.deps.db import SessionDep
from app.models.user import User

bearer = HTTPBearer()


# Authenticates the request: decodes the bearer JWT, sets the RLS user context, and loads the user.
# Raises 401 on any invalid, expired, or revoked (session_epoch mismatch) token.
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
        raw_sub = payload.get("sub")
        user_id: int | None = int(raw_sub) if raw_sub is not None else None
        token_epoch: int | None = payload.get("session_epoch")
        if user_id is None or token_epoch is None:
            raise invalid
    except (JWTError, ValueError):
        raise invalid

    # Set the RLS context from the trusted token before any DB read so the user's own row is
    # visible under the users policy, and the rest of the request runs scoped to this user.
    set_session_user(session, user_id)

    user = await session.get(User, user_id)
    if user is None:
        raise invalid

    if user.session_epoch != token_epoch:
        raise invalid

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# Authorizes an admin: the authenticated user must have is_admin set, else 403. Gates the admin
# invite endpoints (the real access control; RLS on the invites table is only defense-in-depth).
async def get_admin_user(current_user: CurrentUser) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


AdminUser = Annotated[User, Depends(get_admin_user)]
