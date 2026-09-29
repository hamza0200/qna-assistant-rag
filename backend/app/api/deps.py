"""Shared FastAPI dependencies (DB session, current user)."""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import get_db

__all__ = ["get_db", "get_current_user"]

# auto_error=False so we can return our own consistent error shape.
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the bearer JWT to a User, or raise 401.

    The user is re-loaded from the DB on every request, so deleting a user
    immediately revokes access even though their JWT hasn't expired.
    """
    unauthorized = AppError(401, "UNAUTHORIZED", "Invalid or missing authentication token")
    if credentials is None:
        raise unauthorized
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise unauthorized
    user = await db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user
