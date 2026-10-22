"""Cross-encoder reranking: reorders the fused candidate list by scoring
(query, chunk) pairs together, which understands relationships bi-encoder
retrieval can't - e.g. 'who is CEO' vs a signature block where the right
name/title pairing matters. ms-marco-MiniLM-L-6-v2 is ~90MB and scores 20
pairs in well under a second on CPU.

Failure of the model (not downloaded, OOM) must never break search -
callers fall back to the fused order.
"""

import logging
from functools import lru_cache

from app.config import get_settings

logger = logging.getLogger("strata.reranker")


@lru_cache
def _model():
    from sentence_transformers import CrossEncoder  # heavy import, load lazily

    return CrossEncoder(get_settings().reranker_model, max_length=512, device="cpu")


def rerank_scores(query: str, texts: list[str]) -> list[float] | None:
    """Relevance score per text (higher = better); None if the model is unavailable."""
    if not texts:
        return []
    try:
        return [float(s) for s in _model().predict([(query, t) for t in texts])]
    except Exception as exc:  # model download/RAM issues - degrade, don't fail
        logger.warning("reranker unavailable, keeping fused order: %s", exc)
        return None
