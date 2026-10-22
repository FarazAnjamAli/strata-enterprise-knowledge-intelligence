import logging
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.local_provider import LocalAuthProvider
from app.auth.provider import AuthProvider, Identity, InvalidTokenError
from app.auth.rbac import ROLE_ADMIN, ROLE_MEMBER
from app.config import get_settings
from app.database.db import get_db
from app.database.models import User

logger = logging.getLogger("strata.auth")

ACCESS_COOKIE = "strata_at"
REFRESH_COOKIE = "strata_rt"
SESSION_COOKIE = "strata_session"
CSRF_HEADER = "x-strata-csrf"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@lru_cache
def get_auth_provider() -> AuthProvider:
    """Single switch point for the identity backend."""
    s = get_settings()
    if s.auth_provider == "supabase":
        from app.auth.supabase_provider import SupabaseAuthProvider

        return SupabaseAuthProvider(s.supabase_url, s.supabase_jwt_secret)
    return LocalAuthProvider()


def _extract_token(request: Request) -> tuple[str | None, bool]:
    """(token, came_from_cookie). Bearer header wins over cookie."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None, False
    return request.cookies.get(ACCESS_COOKIE), True


def _resolve_user(db: Session, identity: Identity) -> User | None:
    if identity.user_id is not None:
        return db.get(User, identity.user_id)
    user = db.scalar(select(User).where(User.external_id == identity.external_id))
    if user is None and identity.email:
        # link an admin-precreated row on the user's first sign-in
        user = db.scalar(select(User).where(User.email == identity.email, User.external_id.is_(None)))
        if user is not None:
            user.external_id = identity.external_id
    if user is None:
        # external IdP, first login: provision with the least-privileged role
        user = User(email=identity.email, external_id=identity.external_id, role=ROLE_MEMBER, is_active=True)
        db.add(user)
        db.flush()
    return user


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    provider: Annotated[AuthProvider, Depends(get_auth_provider)],
) -> User:
    token, from_cookie = _extract_token(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    # Cookie auth is ambient, so state-changing calls must also carry a custom
    # header a cross-site form can't set (CSRF defence; SameSite=Lax is layer 2)
    if from_cookie and request.method not in _SAFE_METHODS and not request.headers.get(CSRF_HEADER):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing CSRF header")
    try:
        identity = provider.verify_token(token)
    except InvalidTokenError as exc:
        logger.info("token rejected: %s", exc)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    user = _resolve_user(db, identity)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    # refresh last_login at most every 15 min - avoids a write per request
    now = datetime.now(UTC).replace(tzinfo=None)
    if user.last_login is None or now - user.last_login > timedelta(minutes=15):
        user.last_login = now
    if db.dirty or db.new:
        db.commit()
        db.refresh(user)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != ROLE_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
