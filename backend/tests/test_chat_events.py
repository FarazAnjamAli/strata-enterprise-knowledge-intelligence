"""The chat event pipeline, with retrieval results and the LLM faked."""

from app.api import chat
from app.api.chat import Prepared, _MarkerFilter, events, smalltalk_reply, split_used
from app.llm import router
from app.llm.router import ModelInfo
from app.rag.search import SearchHit

INFO = ModelInfo(tier="local", tier_label="Local model", provider="Ollama", model="llama")


def _hit(fid, name, text="Revenue grew in Q3."):
    return SearchHit(
        chunk_id=fid,
        file_id=fid,
        file_name=name,
        page=1,
        section=None,
        text=f"[Document: {name}]\n{text}",
        score=1.0,
        similarity=0.8,
    )


def _fake_stream(tokens, raises=None):
    def fake(*a, **k):
        if raises:
            raise raises
        yield "model", INFO
        for t in tokens:
            yield "token", t

    return fake


def _run(p, monkeypatch, tokens=(), raises=None, allow_paid=False):
    monkeypatch.setattr(chat.llm, "stream", _fake_stream(tokens, raises))
    return list(events(p, user_id=1, role="Member", allow_paid=allow_paid))


def _docs(hits):
    return Prepared(
        "q", "documents", "From your documents", hits=hits, sources=[chat._source(h) for h in hits]
    )


def test_marker_never_reaches_client(monkeypatch):
    p = _docs([_hit(1, "report.pdf"), _hit(2, "other.pdf", "unrelated")])
    out = _run(p, monkeypatch, ["Revenue grew.", "\nUSED_DOC", "UMENTS: report"])
    shown = "".join(d["t"] for e, d in out if e == "token")
    assert "USED" not in shown and shown.startswith("Revenue grew.")
    done = out[-1][1]
    assert [s["file_name"] for s in done["sources"]] == ["report.pdf"]
    assert done["confidence"] == 80 and done["model"]["tier"] == "local"


def test_no_answer_in_context_replaced(monkeypatch):
    out = _run(_docs([_hit(1, "a.pdf")]), monkeypatch, ["NO_ANSWER_IN_CONTEXT"])
    assert any(e == "replace" for e, _ in out)
    assert out[-1][1]["confidence"] == 0


def test_paid_confirmation_surfaces(monkeypatch):
    exc = router.PaidConfirmationRequired(ModelInfo("paid", "Premium API", "OpenAI", "gpt"), 0.002)
    out = _run(_docs([_hit(1, "a.pdf")]), monkeypatch, raises=exc)
    assert out[-1][0] == "paid_required"
    assert out[-1][1]["estimated_cost_usd"] == 0.002


def test_llm_down_returns_excerpts(monkeypatch):
    out = _run(_docs([_hit(1, "a.pdf")]), monkeypatch, raises=router.LLMUnavailable())
    replaced = next(d["answer"] for e, d in out if e == "replace")
    assert "Revenue grew in Q3" in replaced


def test_direct_answer_skips_llm(monkeypatch):
    p = Prepared("hi", "assistant", "Assistant", direct_answer="Hello.")
    out = _run(p, monkeypatch, raises=AssertionError("LLM must not be called"))
    assert [e for e, _ in out] == ["meta", "token", "done"]


def test_marker_filter_passes_lookalikes():
    f = _MarkerFilter()
    out = f.feed("USED") + f.feed(" car sales") + f.flush()
    assert out == "USED car sales"


def test_split_used():
    a, names = split_used("Answer.\nUSED_DOCUMENTS: a, b.pdf")
    assert a == "Answer." and names == ["a", "b.pdf"]


def test_smalltalk():
    assert smalltalk_reply("hello!", "Ana").startswith("Hello Ana")
    assert smalltalk_reply("what is our leave policy", None) is None
