from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError
from app.db.session import get_db_session
from app.models.user import User
from app.services.auth_service import AuthService

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: DbSession,
    settings: AppSettings,
) -> User:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise AuthenticationError()
    return await AuthService(session, settings).authenticate_access_token(credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]
