"""Question answering.

Retrieval decides WHAT the answer is grounded in (the "mode"):
  assistant  greeting / identity - answered directly, no retrieval, no LLM
  documents  hybrid search over every file the user may read (cited)
  file       the same, scoped to one file (isolated analysis)
  clarify    near-identical content in several files - ask which one
  video      best hit is a video (metadata only) - return the play link
  general    nothing matched - general knowledge, clearly labelled

The LLM router decides WHO writes it: local model -> free API -> paid API
(see app/llm/router.py). Both endpoints share one event pipeline;
/stream emits it as Server-Sent Events, /query collects it into JSON.

SSE events: meta -> model -> token* -> [replace] [sources] -> done
            or paid_required (the UI asks, then resends with allow_paid)
            or error
"""

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.auth.rbac import visible_files_filter
from app.config import get_settings
from app.database.db import SessionLocal, get_db
from app.database.models import File, User
from app.llm import prompts
from app.llm import router as llm
from app.rag import memory
from app.rag.search import (
    SearchHit,
    confidence_score,
    detect_duplicates,
    hybrid_search,
    match_file_by_name,
)
from app.security.audit import log_action
from app.security.rate_limit import RateLimited
from app.security.sanitizer import sanitize_query

logger = logging.getLogger("strata.chat")

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ------------------------------------------------------------------ schemas


class Source(BaseModel):
    file_id: int
    file_name: str
    page: int | None
    section: str | None
    snippet: str


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=64)
    file_id: int | None = None  # set -> single-file analysis
    allow_paid: bool = False  # user approved the premium tier for this request


class ModelOut(BaseModel):
    tier: str
    tier_label: str
    provider: str
    model: str


class PaidRequired(BaseModel):
    provider: str
    model: str
    estimated_cost_usd: float


class QueryResponse(BaseModel):
    answer: str
    mode: str
    mode_label: str
    confidence: int
    sources: list[Source]
    model: ModelOut | None = None
    paid_required: PaidRequired | None = None


# --------------------------------------------------------------- smalltalk

_GREETING = re.compile(
    r"^(hi+|hey+|hello+|yo|hola|salam|as*salam[ou]?\s*[ao]?la[iy]kum|"
    r"good\s*(morning|afternoon|evening|day)|how\s*(are|r)\s*(you|u))[\s!.,?]*$",
    re.IGNORECASE,
)
_THANKS = re.compile(r"^(thanks?|thank\s*you|thx|cheers)[\s!.,?]*$", re.IGNORECASE)
_BYE = re.compile(r"^(bye|goodbye|see\s*(you|ya))[\s!.,?]*$", re.IGNORECASE)
_IDENTITY = re.compile(
    r"\b(who|what)\s+(are|r)\s+(you|u)\b|\byour\s+name\b|\bintroduce\s+yourself\b|"
    r"\bwhat\s+can\s+(you|u)\s+do\b",
    re.IGNORECASE,
)


def smalltalk_reply(q: str, first_name: str | None) -> str | None:
    """Conversational input never goes through retrieval - a greeting matched
    against random chunks produces nonsense."""
    name = get_settings().app_name
    if _IDENTITY.search(q):
        return (
            f"I'm **{name}**, your organization's knowledge assistant. I answer "
            "from the documents you have access to and cite every source. "
            "Type `/file` to question a single document, or just ask."
        )
    if _GREETING.match(q):
        hello = f"Hello {first_name}." if first_name else "Hello."
        return f"{hello} Ask me anything about your documents - I'll answer with sources."
    if _THANKS.match(q):
        return "You're welcome. Anything else you'd like to find?"
    if _BYE.match(q):
        return "Goodbye - come back any time."
    return None


# ------------------------------------------------------------------ helpers

_VIDEO_MARKER = "Video file. Format:"
_USED_RE = re.compile(rf"\n?\s*{prompts.USED_MARKER}\s*:\s*(.+?)\s*$", re.IGNORECASE | re.DOTALL)
_NAME_NORM = re.compile(r"[^a-z0-9]+")


def split_used(answer: str) -> tuple[str, list[str] | None]:
    """Strip the trailing USED_DOCUMENTS line; return the names it listed."""
    m = _USED_RE.search(answer)
    if not m:
        return answer, None
    names = [n.strip(" .*`'\"[]") for n in m.group(1).split(",") if n.strip()]
    return answer[: m.start()].rstrip(), names or None


def matches_used(file_name: str, used: list[str]) -> bool:
    stem = _NAME_NORM.sub(" ", Path(file_name).stem.lower()).strip()
    for u in (_NAME_NORM.sub(" ", n.lower()).strip() for n in used):
        if u and (u == stem or u in stem or stem in u):
            return True
    return False


def _no_answer(nothing_found: bool) -> str:
    if nothing_found:
        return (
            "I couldn't find this in the documents you can access. The owning "
            "team may hold a file that isn't shared with you yet - browse "
            "**Access** to request it."
        )
    return "The matching documents don't answer this question. Try rephrasing, or ask the owning team."


def _duplicate_prompt(names: list[str]) -> str:
    listed = "\n".join(f"- **{n}**" for n in names)
    return (
        "I found near-identical content in more than one document. Which one "
        f"did you mean?\n\n{listed}\n\nMention its name, or use `/file` to "
        "question it in isolation."
    )


def _source(h: SearchHit) -> dict:
    return {
        "file_id": h.file_id,
        "file_name": h.file_name,
        "page": h.page,
        "section": h.section,
        "snippet": h.text[:300],
    }


class _MarkerFilter:
    """Withholds the trailing USED_DOCUMENTS line from a token stream:
    buffers any tail that might be the marker's start and releases it once
    it turns out to be ordinary text."""

    def __init__(self, marker: str = prompts.USED_MARKER):
        self.marker, self.pending, self.hiding = marker, "", False

    def feed(self, tok: str) -> str:
        if self.hiding:
            return ""
        self.pending += tok
        idx = self.pending.find(self.marker)
        if idx != -1:
            out, self.pending, self.hiding = self.pending[:idx].rstrip(), "", True
            return out
        keep = next(
            (
                k
                for k in range(min(len(self.marker), len(self.pending)), 0, -1)
                if self.pending.endswith(self.marker[:k])
            ),
            0,
        )
        out = self.pending[: len(self.pending) - keep]
        self.pending = self.pending[len(self.pending) - keep :]
        return out

    def flush(self) -> str:
        out, self.pending = ("" if self.hiding else self.pending), ""
        return out


# ------------------------------------------------------------------ pipeline


@dataclass
class Prepared:
    q: str
    mode: str
    mode_label: str
    hits: list[SearchHit] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    direct_answer: str | None = None  # answered without an LLM
    sources: list[dict] = field(default_factory=list)


def prepare(db: Session, user: User, body: QueryRequest) -> Prepared:
    """All database work happens here, before any streaming starts."""
    q = sanitize_query(body.query)
    if not q:
        raise HTTPException(422, "Query is empty after sanitization")

    first = (user.full_name or "").split(" ")[0] or None
    if (reply := smalltalk_reply(q, first)) is not None:
        return Prepared(q, "assistant", "Assistant", direct_answer=reply)

    scoped = body.file_id is not None
    if scoped:
        target = db.scalar(select(File).where(File.id == body.file_id, visible_files_filter(user)))
        if target is None:
            raise HTTPException(404, "File not found")

    # a query that spells out a file name searches that file only
    target_id = body.file_id if scoped else match_file_by_name(db, user, q)
    hits = hybrid_search(db, q, user, file_id=target_id)
    history = memory.get_history(user.id, body.session_id) if body.session_id else []
    n = get_settings().context_chunks

    if hits and _VIDEO_MARKER in hits[0].text:
        v = hits[0]
        return Prepared(
            q,
            "video",
            "Video file",
            hits=[v],
            direct_answer=(
                f"Here is **{v.file_name}**. Videos are matched by name and metadata "
                "only - they aren't transcribed."
            ),
            sources=[_source(v)],
        )

    if not scoped and (dups := detect_duplicates(hits)):
        return Prepared(
            q,
            "clarify",
            "Clarification needed",
            hits=hits,
            direct_answer=_duplicate_prompt(dups),
            sources=[_source(h) for h in hits[:n] if h.file_name in dups],
        )

    if hits:
        label = f"Only {hits[0].file_name}" if scoped else "From your documents"
        return Prepared(
            q,
            "file" if scoped else "documents",
            label,
            hits=hits[:n],
            history=history,
            sources=[_source(h) for h in hits[:n]],
        )

    if scoped:
        return Prepared(q, "file", "Single file", direct_answer=_no_answer(True))
    return Prepared(q, "general", "General knowledge - not from your documents", history=history)


def events(p: Prepared, *, user_id: int, role: str | None, allow_paid: bool) -> Iterator[tuple[str, dict]]:
    """The answer as a sequence of (event, data). Pure: no request objects."""
    s = get_settings()
    yield "meta", {"mode": p.mode, "mode_label": p.mode_label, "sources": p.sources}

    if p.direct_answer is not None:
        yield "token", {"t": p.direct_answer}
        conf = confidence_score(p.hits) if p.mode == "video" else 0
        yield "done", {"answer": p.direct_answer, "confidence": conf, "model": None, "sources": p.sources}
        return

    grounded = p.mode in ("documents", "file")
    if grounded:
        context = [h.text[: s.context_chunk_chars] for h in p.hits]
        system, prompt = prompts.rag_system(), prompts.rag_prompt(p.q, context, p.history)
    else:
        system, prompt = prompts.general_system(), prompts.general_prompt(p.q, p.history)

    raw: list[str] = []
    model: dict | None = None
    filt = _MarkerFilter()
    try:
        for kind, value in llm.stream(system, prompt, user_id=user_id, role=role, allow_paid=allow_paid):
            if kind == "model":
                model = value.as_dict()  # type: ignore[union-attr]
                yield "model", model
            elif kind == "token":
                raw.append(value)  # type: ignore[arg-type]
                if visible := filt.feed(value):  # type: ignore[arg-type]
                    yield "token", {"t": visible}
            elif kind == "error":
                yield "error", {"message": value}
        if tail := filt.flush():
            yield "token", {"t": tail}
    except llm.PaidConfirmationRequired as exc:
        yield (
            "paid_required",
            {
                "provider": exc.info.provider,
                "model": exc.info.model,
                "estimated_cost_usd": exc.estimated_cost_usd,
            },
        )
        return
    except llm.LLMUnavailable:
        if grounded:
            # graceful degradation: hand back the retrieved excerpts themselves
            excerpts = "\n\n".join(
                f"**{h.file_name}{f' - {h.section}' if h.section else ''}**\n\n{h.text}" for h in p.hits
            )
            answer = (
                "No language model is reachable right now, so here are the most "
                f"relevant excerpts from your documents.\n\n{excerpts}"
            )
        else:
            answer = _no_answer(True)
        yield "replace", {"answer": answer}
        yield "done", {"answer": answer, "confidence": 0, "model": None, "sources": p.sources}
        return

    answer, used = split_used("".join(raw))
    sources = p.sources
    confidence = 0
    if grounded and prompts.NO_ANSWER_IN_CONTEXT in answer:
        answer = _no_answer(False)
        yield "replace", {"answer": answer}
    elif not grounded and re.search(rf"\b{prompts.NO_ANSWER}\b", answer):
        answer = _no_answer(True)
        yield "replace", {"answer": answer}
    elif grounded:
        confidence = confidence_score(p.hits)
        if used:
            kept = [x for x in sources if matches_used(x["file_name"], used)]
            if kept and len(kept) < len(sources):
                sources = kept
                yield "sources", {"sources": sources}
    yield "done", {"answer": answer, "confidence": confidence, "model": model, "sources": sources}


def _bookkeep(
    p: Prepared,
    *,
    user_id: int,
    session_id: str | None,
    answer: str,
    confidence: int,
    model: dict | None,
    sources: list[dict],
    ip: str | None,
) -> None:
    if session_id:
        memory.append(user_id, session_id, "user", p.q)
        memory.append(user_id, session_id, "assistant", answer[:2000])
    with SessionLocal() as db:
        log_action(
            db,
            User(id=user_id),
            "chat.query",
            "chat",
            None,
            details={
                "query": p.q[:500],
                "mode": p.mode,
                "confidence": confidence,
                "tier": model["tier"] if model else None,
                "model": model["model"] if model else None,
                "source_file_ids": [x["file_id"] for x in sources],
            },
            ip_address=ip,
        )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ----------------------------------------------------------------- endpoints


@router.post("/stream")
def stream(
    body: QueryRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    _rl: RateLimited,
) -> StreamingResponse:
    p = prepare(db, user, body)
    user_id, role, ip = user.id, user.role, (request.client.host if request.client else None)

    def gen() -> Iterator[str]:
        for event, data in events(p, user_id=user_id, role=role, allow_paid=body.allow_paid):
            if event == "done":
                _bookkeep(
                    p,
                    user_id=user_id,
                    session_id=body.session_id,
                    answer=data["answer"],
                    confidence=data["confidence"],
                    model=data["model"],
                    sources=data["sources"],
                    ip=ip,
                )
                data = {k: v for k, v in data.items() if k not in ("answer", "sources")}
            yield _sse(event, data)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/query", response_model=QueryResponse)
def query(
    body: QueryRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    _rl: RateLimited,
) -> QueryResponse:
    p = prepare(db, user, body)
    ip = request.client.host if request.client else None
    out = QueryResponse(
        answer="",
        mode=p.mode,
        mode_label=p.mode_label,
        confidence=0,
        sources=[Source(**x) for x in p.sources],
    )
    parts: list[str] = []
    for event, data in events(p, user_id=user.id, role=user.role, allow_paid=body.allow_paid):
        if event == "token":
            parts.append(data["t"])
        elif event == "model":
            out.model = ModelOut(**data)
        elif event == "paid_required":
            out.paid_required = PaidRequired(**data)
        elif event == "done":
            out.answer = data["answer"]
            out.confidence = data["confidence"]
            out.sources = [Source(**x) for x in data["sources"]]
            _bookkeep(
                p,
                user_id=user.id,
                session_id=body.session_id,
                answer=out.answer,
                confidence=out.confidence,
                model=data["model"],
                sources=data["sources"],
                ip=ip,
            )
    if not out.answer and parts and not out.paid_required:
        out.answer = "".join(parts)
    return out


@router.delete("/sessions/{session_id}", status_code=204)
def clear_session(session_id: str, user: CurrentUser) -> None:
    """Forget server-side conversation memory for one chat."""
    memory.clear(user.id, session_id[:64])
