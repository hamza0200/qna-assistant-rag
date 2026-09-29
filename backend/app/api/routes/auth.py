"""Registration, login and current-user routes."""

import logging

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.errors import AppError
from app.core.rate_limit import limiter, login_limit
from app.core.security import DUMMY_HASH, create_access_token, hash_password, verify_password
from app.db.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> User:
    """Create an account. Emails are unique (case-insensitive)."""
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # Relying on the unique index (not a SELECT-then-INSERT) avoids a race
        # where two concurrent registrations both pass the existence check.
        await db.rollback()
        raise AppError(409, "EMAIL_TAKEN", "An account with this email already exists") from None
    await db.refresh(user)
    logger.info("user_registered", extra={"user_id": str(user.id)})
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit(login_limit)
async def login(
    request: Request,  # required by slowapi to key the rate limit
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange email + password for a JWT access token."""
    user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    # Always run bcrypt, even for unknown emails, so response time doesn't reveal
    # which emails are registered (user enumeration via timing).
    valid = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not valid:
        # One generic message for both cases (no user enumeration via messages).
        raise AppError(401, "INVALID_CREDENTIALS", "Incorrect email or password")
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
