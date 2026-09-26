"""
Admin logins: bcrypt password hashes in the users table, and signed
bearer tokens (JWT) for the admin API.

Roles:
  owner - everything, including managing users and editing agent personas
  staff - inventory only
"""

import logging
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import database

logger = logging.getLogger(__name__)

TOKEN_TTL = timedelta(hours=12)
MIN_PASSWORD_LENGTH = 10

_bearer = HTTPBearer(auto_error=False)
_fallback_secret = None


def _jwt_secret():
    secret = os.environ.get("ADMIN_JWT_SECRET", "").strip()
    if secret:
        return secret
    # Fine for local dev; in production set ADMIN_JWT_SECRET (render.yaml
    # generates one) or every restart logs everyone out.
    global _fallback_secret
    if _fallback_secret is None:
        logger.warning("ADMIN_JWT_SECRET not set - using a temporary secret")
        _fallback_secret = secrets.token_urlsafe(32)
    return _fallback_secret


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def validate_new_password(password: str):
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )


def generate_temp_password() -> str:
    return secrets.token_urlsafe(9)  # 12 characters


def issue_token(user: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user["id"]),
        "ver": user["token_version"],
        "iat": now,
        "exp": now + TOKEN_TTL,
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "must_change_password": user["must_change_password"],
        "created_at": user["created_at"],
    }


# ---------- login throttling ----------
# In-memory, per email: enough to slow down password guessing on a single
# small instance. Resets on restart.

MAX_FAILED_LOGINS = 5
LOCKOUT_SECONDS = 15 * 60
_failed_logins: dict[str, list[float]] = {}
_failed_lock = threading.Lock()


def _recent_failures(email: str):
    cutoff = time.monotonic() - LOCKOUT_SECONDS
    attempts = [t for t in _failed_logins.get(email, []) if t > cutoff]
    _failed_logins[email] = attempts
    return attempts


def check_login_allowed(email: str):
    with _failed_lock:
        if len(_recent_failures(email)) >= MAX_FAILED_LOGINS:
            raise HTTPException(
                status_code=429,
                detail="Too many failed attempts. Try again in 15 minutes.",
            )


def record_login_failure(email: str):
    with _failed_lock:
        _recent_failures(email).append(time.monotonic())


def clear_login_failures(email: str):
    with _failed_lock:
        _failed_logins.pop(email, None)


# ---------- request dependencies ----------

def _unauthorized():
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def current_user_allow_password_change(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
):
    """Logged-in user, even if they still have to change a temporary password."""
    if creds is None:
        raise _unauthorized()
    try:
        payload = jwt.decode(creds.credentials, _jwt_secret(), algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _unauthorized()
    user = database.get_user(user_id)
    if not user or user["token_version"] != payload.get("ver"):
        raise _unauthorized()
    return user


def current_user(user: dict = Depends(current_user_allow_password_change)):
    if user["must_change_password"]:
        raise HTTPException(status_code=403, detail="Set a new password first.")
    return user


def require_owner(user: dict = Depends(current_user)):
    if user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only owners can do this.")
    return user


# ---------- first owner ----------

def bootstrap_owner():
    """Create the first owner from ADMIN_EMAIL / ADMIN_PASSWORD when there are
    no users yet. Does nothing once any user exists."""
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if database.count_users() > 0 or not email:
        return
    if len(password) < MIN_PASSWORD_LENGTH:
        logger.warning(
            "ADMIN_EMAIL is set but ADMIN_PASSWORD is missing or shorter than "
            "%d characters - no owner account created", MIN_PASSWORD_LENGTH,
        )
        return
    database.create_user(email, hash_password(password), "owner", must_change_password=False)
    logger.info("Created first owner account for %s", email)
