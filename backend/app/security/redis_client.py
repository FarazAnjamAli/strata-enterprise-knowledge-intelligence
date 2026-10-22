"""One shared Redis connection pool for the process."""

from functools import lru_cache

import redis as redis_lib

from app.config import get_settings


@lru_cache
def get_redis() -> redis_lib.Redis:
    return redis_lib.from_url(
        get_settings().redis_url, socket_connect_timeout=2, socket_timeout=5, health_check_interval=30
    )
