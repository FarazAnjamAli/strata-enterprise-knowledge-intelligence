"""Tier router: walks LLM_TIER_ORDER (default local -> free -> paid) and
returns the first successful completion.

Guarantees
  * External tiers (free, paid) only ever see financially-masked text.
  * A failing tier is skipped for LLM_CIRCUIT_COOLDOWN seconds (circuit
    breaker), so one dead backend doesn't add its timeout to every request.
  * The paid tier is gated by role allow-list, monthly budget, and - when
    PAID_LLM_REQUIRE_CONFIRMATION is on - an explicit per-request opt-in.
    Without it the router raises PaidConfirmationRequired so the UI can ask.
  * Every attempt (success or failure) is written to llm_usage.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from functools import lru_cache

from app.config import TierName, get_settings
from app.llm import usage
from app.llm.providers import Provider, ProviderError, build_providers, estimate_tokens
from app.security.masking import mask_financial_data

logger = logging.getLogger("strata.llm")

TIER_LABELS: dict[str, str] = {"local": "Local model", "free": "Free API", "paid": "Premium API"}


class LLMUnavailable(Exception):
    """No tier could answer."""


@dataclass(frozen=True)
class ModelInfo:
    tier: str
    tier_label: str
    provider: str
    model: str

    def as_dict(self) -> dict:
        return asdict(self)


class PaidConfirmationRequired(Exception):
    def __init__(self, info: ModelInfo, estimated_cost_usd: float):
        super().__init__("paid tier requires confirmation")
        self.info = info
        self.estimated_cost_usd = estimated_cost_usd


def _info(p: Provider) -> ModelInfo:
    return ModelInfo(tier=p.tier, tier_label=TIER_LABELS[p.tier], provider=p.label, model=p.model)


@lru_cache
def providers() -> dict[TierName, Provider]:
    return build_providers()


# ------------------------------------------------------------ circuit breaker

_breaker_lock = threading.Lock()
_breaker_until: dict[str, float] = {}


def _trip(tier: str) -> None:
    with _breaker_lock:
        _breaker_until[tier] = time.monotonic() + get_settings().llm_circuit_cooldown


def _reset(tier: str) -> None:
    with _breaker_lock:
        _breaker_until.pop(tier, None)


def _is_open(tier: str) -> bool:
    with _breaker_lock:
        return _breaker_until.get(tier, 0.0) > time.monotonic()


# ------------------------------------------------------------------- planning


def _paid_allowed(role: str | None) -> bool:
    s = get_settings()
    roles = s.paid_roles
    if roles and (role or "") not in roles:
        return False
    return usage.paid_budget_left() > 0


def plan(role: str | None) -> list[Provider]:
    """Eligible providers in the order they will be tried.

    Tiers whose circuit is open go to the back of the line instead of being
    dropped (half-open retry): if everything healthy fails, a recently failed
    local/free tier gets another chance before anyone is told "unavailable".
    The paid tier is never retried that way - it costs money.
    """
    closed, half_open = [], []
    for tier in get_settings().tier_order:
        p = providers()[tier]
        if not p.configured:
            continue
        if tier == "paid" and not _paid_allowed(role):
            continue
        if not _is_open(tier):
            closed.append(p)
        elif tier != "paid":
            half_open.append(p)
    return closed + half_open


def _prepare(p: Provider, prompt: str) -> str:
    s = get_settings()
    if p.tier != "local" or s.mask_local_llm:
        return mask_financial_data(prompt)
    return prompt


def _gate_paid(p: Provider, system: str, prompt: str, allow_paid: bool) -> None:
    s = get_settings()
    if p.tier == "paid" and s.paid_llm_require_confirmation and not allow_paid:
        est = usage.paid_cost(estimate_tokens(system + prompt), s.llm_max_tokens // 2)
        raise PaidConfirmationRequired(_info(p), est)


# -------------------------------------------------------------------- public


def generate(
    system: str, prompt: str, *, user_id: int | None, role: str | None, allow_paid: bool = False
) -> tuple[str, ModelInfo]:
    for p in plan(role):
        _gate_paid(p, system, prompt, allow_paid)
        started = time.perf_counter()
        try:
            text, u = p.generate(system, _prepare(p, prompt))
        except ProviderError as exc:
            logger.warning("tier %s failed: %s", p.tier, exc)
            _trip(p.tier)
            usage.record(
                user_id=user_id,
                tier=p.tier,
                provider=p.label,
                model=p.model,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=int((time.perf_counter() - started) * 1000),
                success=False,
                error=str(exc),
            )
            continue
        _reset(p.tier)
        usage.record(
            user_id=user_id,
            tier=p.tier,
            provider=p.label,
            model=p.model,
            prompt_tokens=u.prompt_tokens,
            completion_tokens=u.completion_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
            success=True,
        )
        return text, _info(p)
    raise LLMUnavailable("no LLM tier is available")


def stream(
    system: str, prompt: str, *, user_id: int | None, role: str | None, allow_paid: bool = False
) -> Iterator[tuple[str, object]]:
    """Yields ("model", ModelInfo) once a tier starts answering, then
    ("token", str)*. A tier that fails before its first token is skipped
    silently; one that dies mid-answer ends the stream with ("error", msg)."""
    for p in plan(role):
        _gate_paid(p, system, prompt, allow_paid)
        prepared = _prepare(p, prompt)
        started = time.perf_counter()
        parts: list[str] = []
        announced = False
        try:
            for tok in p.stream(system, prepared):
                if not announced:
                    announced = True
                    yield "model", _info(p)
                parts.append(tok)
                yield "token", tok
        except ProviderError as exc:
            logger.warning("tier %s stream failed: %s", p.tier, exc)
            _trip(p.tier)
            usage.record(
                user_id=user_id,
                tier=p.tier,
                provider=p.label,
                model=p.model,
                prompt_tokens=estimate_tokens(system + prepared),
                completion_tokens=estimate_tokens("".join(parts)),
                latency_ms=int((time.perf_counter() - started) * 1000),
                success=False,
                error=str(exc),
            )
            if announced:
                yield "error", "The model connection dropped mid-answer."
                return
            continue
        if not announced:
            yield "model", _info(p)
        _reset(p.tier)
        text = "".join(parts)
        usage.record(
            user_id=user_id,
            tier=p.tier,
            provider=p.label,
            model=p.model,
            prompt_tokens=estimate_tokens(system + prepared),
            completion_tokens=estimate_tokens(text),
            latency_ms=int((time.perf_counter() - started) * 1000),
            success=True,
        )
        return
    raise LLMUnavailable("no LLM tier is available")


# -------------------------------------------------------------------- status

_status_lock = threading.Lock()
_status_cache: tuple[float, list[dict]] | None = None
_STATUS_TTL = 20.0


def status() -> list[dict]:
    """Per-tier health for the UI, cached briefly (pings hit the network)."""
    global _status_cache
    with _status_lock:
        if _status_cache and time.monotonic() - _status_cache[0] < _STATUS_TTL:
            return _status_cache[1]
    s = get_settings()
    order = s.tier_order
    rows = []
    for tier in ("local", "free", "paid"):
        p = providers()[tier]
        healthy = p.ping() if p.configured else False
        row = {
            "tier": tier,
            "tier_label": TIER_LABELS[tier],
            "provider": p.label,
            "model": p.model,
            "enabled": tier in order and p.configured,
            "position": order.index(tier) + 1 if tier in order else None,
            "healthy": healthy and not _is_open(tier),
            "circuit_open": _is_open(tier),
        }
        if tier == "paid":
            spend = usage.paid_month_spend() if p.configured else 0.0
            row.update(
                {
                    "requires_confirmation": s.paid_llm_require_confirmation,
                    "monthly_budget_usd": s.paid_llm_monthly_budget_usd,
                    "month_spend_usd": round(spend, 4) if spend != float("inf") else None,
                }
            )
        rows.append(row)
    with _status_lock:
        _status_cache = (time.monotonic(), rows)
    return rows
