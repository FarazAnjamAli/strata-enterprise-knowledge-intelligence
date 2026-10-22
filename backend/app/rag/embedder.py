"""Sentence-transformers embedding with a Redis cache.

The model is a lazy process-wide singleton (~430MB RAM). Both the API
(query embedding) and the Celery worker (document embedding) use this.
"""

import hashlib
import struct
from functools import lru_cache

import redis as redis_lib

from app.config import get_settings
from app.security.redis_client import get_redis

_CACHE_PREFIX = "emb:v1:"
_CACHE_TTL = 7 * 24 * 3600


@lru_cache
def _model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_model, device="cpu")


def _redis():
    return get_redis()


def _key(text: str) -> str:
    return _CACHE_PREFIX + hashlib.sha256(text.encode()).hexdigest()


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(raw: bytes) -> list[float]:
    return list(struct.unpack(f"{len(raw) // 4}f", raw))


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts, serving repeats from Redis. Order preserved."""
    settings = get_settings()
    results: list[list[float] | None] = [None] * len(texts)
    to_compute: list[int] = []

    if settings.embedding_cache_enabled:
        try:
            cached = _redis().mget([_key(t) for t in texts])
        except redis_lib.RedisError:
            cached = [None] * len(texts)
        for i, raw in enumerate(cached):
            if raw is not None:
                results[i] = _unpack(raw)
            else:
                to_compute.append(i)
    else:
        to_compute = list(range(len(texts)))

    if to_compute:
        vectors = _model().encode(
            [texts[i] for i in to_compute],
            batch_size=settings.embedding_batch_size,
            show_progress_bar=False,
            normalize_embeddings=False,
        )
        pipe = _redis().pipeline() if settings.embedding_cache_enabled else None
        for i, vec in zip(to_compute, vectors):
            vec_list = vec.tolist()
            results[i] = vec_list
            if pipe is not None:
                pipe.setex(_key(texts[i]), _CACHE_TTL, _pack(vec_list))
        if pipe is not None:
            try:
                pipe.execute()
            except redis_lib.RedisError:
                pass  # cache write failure must never fail embedding

    return results  # type: ignore[return-value]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
