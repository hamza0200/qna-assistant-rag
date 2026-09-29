"""Password hashing and JWT helpers.

bcrypt is deliberately slow (tunable work factor) and salts every hash, so a
leaked `users` table can't be reversed with precomputed rainbow tables.
"""

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

# bcrypt only looks at the first 72 bytes; longer inputs are rejected at the
# schema layer rather than silently truncated.
BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    """Return a salted bcrypt hash (the salt and cost are embedded in the string)."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=get_settings().bcrypt_rounds)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time comparison of a candidate password against a stored hash."""
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:  # malformed hash
        return False


# A real hash of a random string, used to equalize timing when the user doesn't
# exist (otherwise "unknown email" returns measurably faster than "wrong password").
DUMMY_HASH = hash_password(uuid.uuid4().hex)


def create_access_token(user_id: uuid.UUID) -> str:
    """Issue a signed JWT whose `sub` claim is the user ID."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> uuid.UUID | None:
    """Verify signature + expiry and return the user ID, or None if invalid.

    `algorithms=[...]` is pinned explicitly: accepting the algorithm from the
    token header enables the classic `alg: none` / key-confusion attacks.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
        if payload.get("type") != "access":
            return None
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
