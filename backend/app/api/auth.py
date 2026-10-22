"""Session endpoints. Tokens travel as httpOnly cookies for the web app and
are also returned in the body for API/CLI clients (send as Bearer)."""

import logging
from typing import Annotated

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.types import Email
from app.auth import tokens
from app.auth.dependencies import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    SESSION_COOKIE,
    CurrentUser,
    _resolve_user,
    get_auth_provider,
)
from app.auth.passwords import burn_time, hash_password, password_problems, verify_password
from app.auth.provider import InvalidTokenError
from app.config import get_settings
from app.database.db import get_db
from app.database.models import User
from app.security.audit import log_action
from app.security.redis_client import get_redis

logger = logging.getLogger("strata.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

_LOCKOUT_ATTEMPTS = 5
_LOCKOUT_SECONDS = 15 * 60


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=256)


class Profile(BaseModel):
    id: int
    email: str
    full_name: str | None
    department: str | None
    role: str | None
    designation: str | None


class SessionOut(BaseModel):
    user: Profile
    access_token: str
    expires_in: int


def profile_of(u: User) -> Profile:
    return Profile(
        id=u.id,
        email=u.email,
        full_name=u.full_name,
        department=u.department,
        role=u.role,
        designation=u.designation,
    )


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _set_cookies(response: Response, access: str, refresh: str | None) -> None:
    s = get_settings()
    common = {
        "httponly": True,
        "samesite": "lax",
        "secure": s.cookie_secure,
        "domain": s.cookie_domain or None,
    }
    response.set_cookie(ACCESS_COOKIE, access, max_age=s.access_token_minutes * 60, path="/", **common)
    if refresh:
        # scoped to the auth routes: the refresh token never rides along on
        # ordinary API calls
        response.set_cookie(
            REFRESH_COOKIE, refresh, max_age=s.refresh_token_days * 86400, path="/api/auth", **common
        )
        # non-secret marker visible on page routes: lets the web app's edge
        # middleware tell "signed in, access token just expired" from "signed out"
        response.set_cookie(SESSION_COOKIE, "1", max_age=s.refresh_token_days * 86400, path="/", **common)


def _clear_cookies(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(ACCESS_COOKIE, path="/", domain=s.cookie_domain or None)
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth", domain=s.cookie_domain or None)
    response.delete_cookie(SESSION_COOKIE, path="/", domain=s.cookie_domain or None)


# ---------------------------------------------------------------- lockout


def _lock_key(email: str, ip: str | None) -> str:
    return f"auth:fail:v1:{email.lower()}:{ip or '-'}"


def _locked(email: str, ip: str | None) -> bool:
    try:
        return int(get_redis().get(_lock_key(email, ip)) or 0) >= _LOCKOUT_ATTEMPTS
    except redis_lib.RedisError:
        return False


def _note_failure(email: str, ip: str | None) -> None:
    try:
        pipe = get_redis().pipeline()
        pipe.incr(_lock_key(email, ip))
        pipe.expire(_lock_key(email, ip), _LOCKOUT_SECONDS)
        pipe.execute()
    except redis_lib.RedisError:
        pass


def _clear_failures(email: str, ip: str | None) -> None:
    try:
        get_redis().delete(_lock_key(email, ip))
    except redis_lib.RedisError:
        pass


# ---------------------------------------------------------------- endpoints


@router.post("/login", response_model=SessionOut)
def login(
    body: LoginRequest, request: Request, response: Response, db: Annotated[Session, Depends(get_db)]
) -> SessionOut:
    s = get_settings()
    ip = _ip(request)
    email = body.email.lower()
    if _locked(email, ip):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Try again in 15 minutes."
        )

    if s.auth_provider == "supabase":
        from app.auth.supabase_provider import SupabaseError

        provider = get_auth_provider()
        try:
            session = provider.password_login(email, body.password)  # type: ignore[attr-defined]
            identity = provider.verify_token(session["access_token"])
        except (SupabaseError, InvalidTokenError, KeyError):
            _note_failure(email, ip)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
        user = _resolve_user(db, identity)
        access, refresh = session["access_token"], session.get("refresh_token")
        expires = int(session.get("expires_in", 3600))
    else:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            burn_time(body.password)
        if user is None or not verify_password(body.password, user.password_hash):
            _note_failure(email, ip)
            log_action(
                db,
                user,
                "auth.login_failed",
                "user",
                user.id if user else None,
                details={"email": email},
                ip_address=ip,
            )
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
        access = tokens.issue_access(user.id, user.email)
        refresh = tokens.issue_refresh(user.id, user.token_version)
        expires = s.access_token_minutes * 60

    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    _clear_failures(email, ip)
    db.commit()
    _set_cookies(response, access, refresh)
    log_action(db, user, "auth.login", "user", user.id, ip_address=ip)
    return SessionOut(user=profile_of(user), access_token=access, expires_in=expires)


@router.post("/refresh", response_model=SessionOut)
def refresh(request: Request, response: Response, db: Annotated[Session, Depends(get_db)]) -> SessionOut:
    s = get_settings()
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No session")

    if s.auth_provider == "supabase":
        from app.auth.supabase_provider import SupabaseError

        provider = get_auth_provider()
        try:
            session = provider.refresh(token)  # type: ignore[attr-defined]
            identity = provider.verify_token(session["access_token"])
        except (SupabaseError, InvalidTokenError, KeyError):
            _clear_cookies(response)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
        user = _resolve_user(db, identity)
        access, new_refresh = session["access_token"], session.get("refresh_token")
        expires = int(session.get("expires_in", 3600))
    else:
        try:
            claims = tokens.decode(token, "refresh")
            user = db.get(User, int(claims["sub"]))
        except (tokens.TokenError, ValueError):
            user, claims = None, {}
        if user is None or claims.get("ver") != user.token_version:
            _clear_cookies(response)
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
        access = tokens.issue_access(user.id, user.email)
        new_refresh = tokens.issue_refresh(user.id, user.token_version)  # rotation
        expires = s.access_token_minutes * 60

    if user is None or not user.is_active:
        _clear_cookies(response)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    db.commit()
    _set_cookies(response, access, new_refresh)
    return SessionOut(user=profile_of(user), access_token=access, expires_in=expires)


@router.post("/logout", status_code=204)
def logout(response: Response) -> Response:
    _clear_cookies(response)
    response.status_code = 204
    return response


@router.post("/logout-everywhere", status_code=204)
def logout_everywhere(
    user: CurrentUser, request: Request, response: Response, db: Annotated[Session, Depends(get_db)]
) -> Response:
    """Revoke every refresh token this user holds (local auth)."""
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    log_action(db, user, "auth.logout_everywhere", "user", user.id, ip_address=_ip(request))
    _clear_cookies(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=Profile)
def me(user: CurrentUser) -> Profile:
    return profile_of(user)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


@router.post("/password", status_code=204)
def change_password(
    body: PasswordChange,
    user: CurrentUser,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    if get_settings().auth_provider != "local":
        raise HTTPException(422, "Passwords are managed by your identity provider")
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(422, "Current password is incorrect")
    if problems := password_problems(body.new_password):
        raise HTTPException(422, "Password needs " + ", ".join(problems))
    user.password_hash = hash_password(body.new_password)
    user.token_version = (user.token_version or 0) + 1  # sign out other sessions
    db.commit()
    log_action(db, user, "auth.password_change", "user", user.id, ip_address=_ip(request))
    # keep this browser signed in with fresh tokens
    _set_cookies(
        response, tokens.issue_access(user.id, user.email), tokens.issue_refresh(user.id, user.token_version)
    )
    response.status_code = 204
    return response
