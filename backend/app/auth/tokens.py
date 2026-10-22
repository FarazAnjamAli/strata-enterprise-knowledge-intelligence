"""JWTs issued by Strata itself (AUTH_PROVIDER=local).

access , short-lived (ACCESS_TOKEN_MINUTES), sent on every API call
refresh, long-lived (REFRESH_TOKEN_DAYS), only accepted by /auth/refresh,
          carries the user's token_version so bumping it revokes them all
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings

ISSUER = "strata"


class TokenError(Exception):
    pass


def _encode(claims: dict, lifetime: timedelta) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        **claims,
        "iss": ISSUER,
        "iat": now,
        "nbf": now,
        "exp": now + lifetime,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def issue_access(user_id: int, email: str) -> str:
    s = get_settings()
    return _encode(
        {"sub": str(user_id), "email": email, "typ": "access"}, timedelta(minutes=s.access_token_minutes)
    )


def issue_refresh(user_id: int, token_version: int) -> str:
    s = get_settings()
    return _encode(
        {"sub": str(user_id), "ver": token_version, "typ": "refresh"}, timedelta(days=s.refresh_token_days)
    )


def decode(token: str, expected_type: str) -> dict:
    s = get_settings()
    try:
        claims = jwt.decode(
            token,
            s.jwt_secret,
            algorithms=[s.jwt_algorithm],
            issuer=ISSUER,
            options={"require": ["exp", "sub", "typ"]},
            leeway=30,
        )
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if claims.get("typ") != expected_type:
        raise TokenError(f"expected a {expected_type} token")
    return claims
