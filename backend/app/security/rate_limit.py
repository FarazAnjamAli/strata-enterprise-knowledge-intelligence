"""Per-role request rate limiting (Redis fixed window, 60 s).

Limits come from RATE_LIMIT_* settings, plus an IP-wide backup cap. 429 on
violation, audit-logged once per window. Redis being down never blocks a
request (fail open - availability beats strictness for a rate limiter).
"""

import logging
import time
from typing import Annotated

import redis as redis_lib
from fastapi import Depends, HTTPException, Request

from app.auth.dependencies import CurrentUser
from app.auth.rbac import ROLE_ADMIN, ROLE_HEAD, ROLE_MANAGER
from app.config import get_settings
from app.database.db import get_db
from app.security.audit import log_action
from app.security.redis_client import get_redis

logger = logging.getLogger("strata.ratelimit")

_WINDOW = 60


def role_limit(role: str | None) -> int:
    s = get_settings()
    return {
        ROLE_ADMIN: s.rate_limit_admin,
        ROLE_HEAD: s.rate_limit_department_head,
        ROLE_MANAGER: s.rate_limit_manager,
    }.get(role or "", s.rate_limit_member)


def _bump(key: str) -> int:
    pipe = get_redis().pipeline()
    pipe.incr(key)
    pipe.expire(key, _WINDOW)
    return pipe.execute()[0]


def check_rate_limit(request: Request, user: CurrentUser, db=Depends(get_db)) -> None:
    s = get_settings()
    if not s.enable_rate_limiting:
        return
    limit = role_limit(user.role)
    window = int(time.time()) // _WINDOW
    ip = request.client.host if request.client else "unknown"
    try:
        user_count = _bump(f"rl:v1:u:{user.id}:{window}")
        ip_count = _bump(f"rl:v1:ip:{ip}:{window}")
    except redis_lib.RedisError:
        logger.warning("rate limiter Redis unavailable; allowing request")
        return

    if user_count <= limit and ip_count <= s.rate_limit_ip:
        return
    if user_count == limit + 1 or ip_count == s.rate_limit_ip + 1:
        log_action(
            db,
            user,
            "rate_limit.exceeded",
            details={"role": user.role, "limit": limit, "count": user_count},
            ip_address=ip,
        )
    retry = _WINDOW - int(time.time()) % _WINDOW
    raise HTTPException(
        429,
        f"Rate limit reached ({limit}/min for your role). Try again in {retry}s.",
        headers={"Retry-After": str(retry)},
    )


RateLimited = Annotated[None, Depends(check_rate_limit)]
