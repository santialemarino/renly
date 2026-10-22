from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_admin_session, get_auth_session, get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
# Privileged session for authenticated cross-user work (admin surface, group/pot bootstrap); bypasses
# RLS. Do not use for user-scoped request work, nor for a pre-auth path (use AuthSessionDep).
AdminSessionDep = Annotated[AsyncSession, Depends(get_admin_session)]
# Privileged session on the dedicated auth pool, for the pre-auth paths (login, register, refresh,
# verification, password reset, API-key verification); bypasses RLS.
AuthSessionDep = Annotated[AsyncSession, Depends(get_auth_session)]
