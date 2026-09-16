"""Password hashing + JWT helpers."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from .config import settings

ALGORITHM = "HS256"


def _pw_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_pw_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_pw_bytes(password), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, email: str) -> str:
    cfg = settings()
    expire = datetime.now(timezone.utc) + timedelta(hours=int(cfg["jwt_expire_hours"]))
    payload = {"sub": str(user_id), "email": email, "exp": expire}
    return jwt.encode(payload, str(cfg["jwt_secret"]), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    cfg = settings()
    try:
        return jwt.decode(token, str(cfg["jwt_secret"]), algorithms=[ALGORITHM])
    except JWTError:
        return None


def new_email_token() -> str:
    return secrets.token_urlsafe(32)
