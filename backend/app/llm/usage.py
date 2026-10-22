"""Per-call LLM accounting: which tier answered, tokens, latency, cost.

Feeds the admin "Models" view and the paid-tier monthly budget guard.
Writes never raise - accounting must not break a chat answer.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.config import get_settings
from app.database.db import SessionLocal
from app.database.models import LLMUsage

logger = logging.getLogger("strata.llm.usage")


def paid_cost(prompt_tokens: int, completion_tokens: int) -> float:
    s = get_settings()
    return round(
        prompt_tokens / 1_000_000 * s.paid_llm_input_cost_per_mtok
        + completion_tokens / 1_000_000 * s.paid_llm_output_cost_per_mtok,
        6,
    )


def record(
    *,
    user_id: int | None,
    tier: str,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    success: bool,
    error: str | None = None,
) -> None:
    cost = paid_cost(prompt_tokens, completion_tokens) if tier == "paid" and success else 0.0
    try:
        with SessionLocal() as db:
            db.add(
                LLMUsage(
                    user_id=user_id,
                    tier=tier,
                    provider=provider,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                    success=success,
                    error=(error or "")[:500] or None,
                )
            )
            db.commit()
    except Exception:  # pragma: no cover - accounting is best effort
        logger.exception("failed to record llm usage")
    if cost:
        _budget_cache.invalidate()


def _month_start() -> datetime:
    now = datetime.now(UTC).replace(tzinfo=None)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class _BudgetCache:
    """Month-to-date paid spend, cached briefly so the guard costs no query
    on every chat request."""

    TTL = 60.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value = 0.0
        self._at = 0.0

    def invalidate(self) -> None:
        with self._lock:
            self._at = 0.0

    def spend(self) -> float:
        with self._lock:
            if time.monotonic() - self._at < self.TTL:
                return self._value
        try:
            with SessionLocal() as db:
                value = float(
                    db.scalar(
                        select(func.coalesce(func.sum(LLMUsage.cost_usd), 0)).where(
                            LLMUsage.tier == "paid", LLMUsage.created_at >= _month_start()
                        )
                    )
                    or 0
                )
        except Exception:
            logger.exception("budget lookup failed; assuming budget exhausted")
            return float("inf")  # fail closed: never overspend on a DB hiccup
        with self._lock:
            self._value, self._at = value, time.monotonic()
        return value


_budget_cache = _BudgetCache()


def paid_month_spend() -> float:
    return _budget_cache.spend()


def paid_budget_left() -> float:
    return get_settings().paid_llm_monthly_budget_usd - paid_month_spend()
