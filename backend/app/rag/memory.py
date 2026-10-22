"""Session conversation memory: last 10 exchanges in Redis, cleared on
logout or TTL expiry. Keyed by user id + client-supplied session id so
sessions can't be read across users."""

import json

import redis as redis_lib

from app.security.redis_client import get_redis

MAX_MESSAGES = 10
_TTL = 24 * 3600


def _redis():
    return get_redis()


def _key(user_id: int, session_id: str) -> str:
    return f"chat:v1:{user_id}:{session_id}"


def get_history(user_id: int, session_id: str) -> list[dict]:
    try:
        raw = _redis().lrange(_key(user_id, session_id), -MAX_MESSAGES, -1)
        return [json.loads(m) for m in raw]
    except redis_lib.RedisError:
        return []


def append(user_id: int, session_id: str, role: str, content: str) -> None:
    try:
        key = _key(user_id, session_id)
        pipe = _redis().pipeline()
        pipe.rpush(key, json.dumps({"role": role, "content": content}))
        pipe.ltrim(key, -MAX_MESSAGES, -1)
        pipe.expire(key, _TTL)
        pipe.execute()
    except redis_lib.RedisError:
        pass  # memory is a nicety; losing it must not fail the request


def clear(user_id: int, session_id: str) -> None:
    try:
        _redis().delete(_key(user_id, session_id))
    except redis_lib.RedisError:
        pass
