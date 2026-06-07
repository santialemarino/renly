from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_admin_session, get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
# Privileged session for context-less auth bootstrap (login, register, API-key verification);
# bypasses RLS. Do not use for user-scoped request work.
AdminSessionDep = Annotated[AsyncSession, Depends(get_admin_session)]
