"""Tier router behaviour: ordering, fallback, circuit breaker, paid gating,
masking of external tiers."""

from collections.abc import Iterator

import pytest

from app.config import get_settings
from app.llm import router, usage
from app.llm.providers import Provider, ProviderError, Usage


class FakeProvider(Provider):
    def __init__(self, tier, *, fail=False, fail_mid=False, reply="answer"):
        self.tier, self.label, self.model = tier, f"fake-{tier}", f"m-{tier}"
        self.fail, self.fail_mid, self.reply = fail, fail_mid, reply
        self.seen: list[str] = []

    @property
    def configured(self) -> bool:
        return True

    def generate(self, system, prompt):
        self.seen.append(prompt)
        if self.fail:
            raise ProviderError("down")
        return self.reply, Usage(10, 5)

    def stream(self, system, prompt) -> Iterator[str]:
        self.seen.append(prompt)
        if self.fail:
            raise ProviderError("down")
        yield "par"
        if self.fail_mid:
            raise ProviderError("dropped")
        yield "tial"


@pytest.fixture
def tiers(monkeypatch):
    def install(local=None, free=None, paid=None, order="local,free,paid", **settings):
        provs = {
            "local": local or FakeProvider("local"),
            "free": free or FakeProvider("free"),
            "paid": paid or FakeProvider("paid"),
        }
        monkeypatch.setattr(router, "providers", lambda: provs)
        s = get_settings()
        monkeypatch.setattr(s, "llm_tier_order", order)
        for k, v in settings.items():
            monkeypatch.setattr(s, k, v)
        return provs

    monkeypatch.setattr(usage, "record", lambda **kw: None)
    monkeypatch.setattr(usage, "paid_budget_left", lambda: 10.0)
    router._breaker_until.clear()
    yield install
    router._breaker_until.clear()


def test_local_answers_first(tiers):
    p = tiers()
    text, info = router.generate("sys", "q", user_id=1, role="Member")
    assert info.tier == "local" and text == "answer"
    assert not p["free"].seen


def test_falls_back_to_free_and_trips_breaker(tiers):
    p = tiers(local=FakeProvider("local", fail=True))
    _, info = router.generate("sys", "q", user_id=1, role="Member")
    assert info.tier == "free"
    # breaker open: the dead local tier is not even attempted the second time
    router.generate("sys", "q", user_id=1, role="Member")
    assert len(p["local"].seen) == 1


def test_paid_requires_confirmation(tiers):
    tiers(
        local=FakeProvider("local", fail=True),
        free=FakeProvider("free", fail=True),
        paid_llm_require_confirmation=True,
    )
    with pytest.raises(router.PaidConfirmationRequired) as exc:
        router.generate("sys", "q", user_id=1, role="Member")
    assert exc.value.info.tier == "paid"
    _, info = router.generate("sys", "q", user_id=1, role="Member", allow_paid=True)
    assert info.tier == "paid"


def test_paid_skipped_for_disallowed_role(tiers):
    tiers(
        local=FakeProvider("local", fail=True),
        free=FakeProvider("free", fail=True),
        paid_llm_allowed_roles="Admin",
    )
    with pytest.raises(router.LLMUnavailable):
        router.generate("sys", "q", user_id=1, role="Member", allow_paid=True)


def test_paid_skipped_when_budget_exhausted(tiers, monkeypatch):
    tiers(local=FakeProvider("local", fail=True), free=FakeProvider("free", fail=True))
    monkeypatch.setattr(usage, "paid_budget_left", lambda: 0.0)
    with pytest.raises(router.LLMUnavailable):
        router.generate("sys", "q", user_id=1, role="Admin", allow_paid=True)


def test_external_tiers_get_masked_prompt(tiers):
    p = tiers(local=FakeProvider("local", fail=True), mask_local_llm=False)
    router.generate("sys", "salary: 250,000 PKR 9,000", user_id=1, role="Member")
    assert "250,000" not in p["free"].seen[0]
    assert "[MASKED]" in p["free"].seen[0]


def test_local_tier_unmasked_by_default(tiers):
    p = tiers(mask_local_llm=False)
    router.generate("sys", "salary: 250,000", user_id=1, role="Member")
    assert "250,000" in p["local"].seen[0]


def test_tier_order_respected(tiers):
    tiers(order="free,local")
    _, info = router.generate("sys", "q", user_id=1, role="Member")
    assert info.tier == "free"


def test_stream_announces_model_then_tokens(tiers):
    tiers()
    events = list(router.stream("sys", "q", user_id=1, role="Member"))
    assert events[0][0] == "model" and events[0][1].tier == "local"
    assert "".join(v for k, v in events if k == "token") == "partial"


def test_stream_falls_back_before_first_token(tiers):
    tiers(local=FakeProvider("local", fail=True))
    events = list(router.stream("sys", "q", user_id=1, role="Member"))
    assert events[0][1].tier == "free"


def test_stream_mid_answer_failure_reports_error(tiers):
    tiers(local=FakeProvider("local", fail_mid=True))
    events = list(router.stream("sys", "q", user_id=1, role="Member"))
    assert events[-1][0] == "error"
    assert [k for k, _ in events].count("model") == 1


def test_nothing_available(tiers):
    tiers(local=FakeProvider("local", fail=True), free=FakeProvider("free", fail=True), order="local,free")
    with pytest.raises(router.LLMUnavailable):
        list(router.stream("sys", "q", user_id=1, role="Member"))


def test_paid_cost(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "paid_llm_input_cost_per_mtok", 1.0)
    monkeypatch.setattr(s, "paid_llm_output_cost_per_mtok", 2.0)
    assert usage.paid_cost(1_000_000, 500_000) == 2.0


def test_open_circuit_is_retried_last(tiers):
    p = tiers(order="local,free")
    router._trip("local")
    _, info = router.generate("sys", "q", user_id=1, role="Member")
    assert info.tier == "free"  # healthy tier first
    p["free"].fail = True
    _, info = router.generate("sys", "q", user_id=1, role="Member")
    assert info.tier == "local"  # half-open retry of the tripped tier
