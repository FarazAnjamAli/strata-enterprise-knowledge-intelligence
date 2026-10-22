"""Hybrid retrieval: pgvector cosine similarity + Postgres full-text rank,
fused with Reciprocal Rank Fusion. RBAC is part of the SQL, chunks the
user can't see are never ranked or returned.
"""

import difflib
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.rbac import visible_files_filter
from app.config import get_settings
from app.database.models import File, FileChunk, User
from app.rag.embedder import embed_query
from app.rag.reranker import rerank_scores

_RRF_K = 60
_MAX_CHUNKS_PER_FILE = 3  # one huge document must not crowd out every other file

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _norm(s: str) -> str:
    return " ".join(_NON_ALNUM.sub(" ", s.lower()).split())


def match_file_by_name(db: Session, user: User, query: str) -> int | None:
    """Metadata filter: the id of the file whose name the query spells out.

    'participants of MOM-Orientation-Session-23-24Sep2021' should search that
    file, not fight 283 chunks of an unrelated manual. Both sides normalized
    (case/punctuation-insensitive); generic one-word stems like 'document'
    are ignored so ordinary phrasing never accidentally locks onto a file.
    Longest match wins; returns None when nothing (or nothing safe) matches.
    """
    qn = f" {_norm(query)} "
    best_id, best_len = None, 0
    rows = db.execute(
        select(File.id, File.name).where(File.index_status == "ready", visible_files_filter(user))
    ).all()
    for fid, name in rows:
        stem = _norm(Path(name).stem)
        distinctive = " " in stem or len(stem) >= 10
        if distinctive and f" {stem} " in qn and len(stem) > best_len:
            best_id, best_len = fid, len(stem)
    return best_id


@dataclass
class SearchHit:
    chunk_id: int
    file_id: int
    file_name: str
    page: int | None
    section: str | None
    text: str
    score: float
    similarity: float  # cosine similarity of this chunk to the query (0-1)


def hybrid_search(
    db: Session,
    query: str,
    user: User,
    top_k: int | None = None,
    file_id: int | None = None,
) -> list[SearchHit]:
    settings = get_settings()
    top_k = top_k or settings.top_k_results
    fetch = max(settings.rerank_top_k, top_k)

    conditions = [File.is_indexed.is_(True), visible_files_filter(user)]
    if file_id is not None:
        conditions.append(File.id == file_id)

    query_vec = embed_query(query)
    distance = FileChunk.embedding.cosine_distance(query_vec)

    vector_rows = db.execute(
        select(
            FileChunk.id,
            FileChunk.file_id,
            File.name,
            FileChunk.page_number,
            FileChunk.section_title,
            FileChunk.chunk_text,
            distance.label("dist"),
        )
        .join(File, File.id == FileChunk.file_id)
        .where(*conditions, FileChunk.embedding.is_not(None))
        .order_by(distance)
        .limit(fetch)
    ).all()

    tsq = func.websearch_to_tsquery("english", query)
    keyword_rows = db.execute(
        select(
            FileChunk.id,
            FileChunk.file_id,
            File.name,
            FileChunk.page_number,
            FileChunk.section_title,
            FileChunk.chunk_text,
            func.ts_rank(FileChunk.content_tsv, tsq).label("rank"),
        )
        .join(File, File.id == FileChunk.file_id)
        .where(*conditions, FileChunk.content_tsv.op("@@")(tsq))
        .order_by(func.ts_rank(FileChunk.content_tsv, tsq).desc())
        .limit(fetch)
    ).all()

    # Reciprocal Rank Fusion across both result lists
    fused: dict[int, dict] = {}
    for rank, row in enumerate(vector_rows):
        entry = fused.setdefault(
            row.id,
            {"row": row, "score": 0.0, "similarity": max(0.0, 1.0 - float(row.dist))},
        )
        entry["score"] += 1.0 / (_RRF_K + rank + 1)
    for rank, row in enumerate(keyword_rows):
        entry = fused.setdefault(row.id, {"row": row, "score": 0.0, "similarity": 0.0})
        entry["score"] += 1.0 / (_RRF_K + rank + 1)

    ranked = sorted(fused.values(), key=lambda e: e["score"], reverse=True)

    # near-duplicate collapse: SOP manuals repeat the same boilerplate table
    # on every page; six copies of one text must count as one candidate or
    # they push the actually-informative chunk out of the context window
    seen_text: set[str] = set()
    unique = []
    for e in ranked:
        key = " ".join(e["row"].chunk_text.split())
        if key in seen_text:
            continue
        seen_text.add(key)
        unique.append(e)

    hits = [
        SearchHit(
            chunk_id=e["row"].id,
            file_id=e["row"].file_id,
            file_name=e["row"].name,
            page=e["row"].page_number,
            section=e["row"].section_title,
            text=e["row"].chunk_text,
            score=e["score"],
            similarity=e["similarity"],
        )
        for e in unique[: settings.rerank_top_k]
    ]

    # cross-encoder rerank: scores query+chunk together, so the chunk that
    # actually answers outranks chunks that merely share vocabulary
    if settings.enable_reranking and hits:
        scores = rerank_scores(query, [h.text for h in hits])
        if scores is not None:
            paired = sorted(zip(scores, hits), key=lambda p: p[0], reverse=True)
            # ponytail: -10 floor = clear junk on ms-marco logits (unrelated
            # text scores ~-11, messy-but-relevant ~-6); tune if model changes
            kept = [h for s, h in paired if s > -10]
            hits = kept or [paired[0][1]]

    # diversity cap, skipped for single-file (file_id) searches
    if file_id is None:
        per_file: dict[int, int] = {}
        capped = []
        for h in hits:
            per_file[h.file_id] = per_file.get(h.file_id, 0) + 1
            if per_file[h.file_id] <= _MAX_CHUNKS_PER_FILE:
                capped.append(h)
        hits = capped

    return hits[:top_k]


def detect_duplicates(hits: list[SearchHit], threshold: float = 0.9) -> list[str] | None:
    """File names of near-identical top hits living in DIFFERENT files.

    Two >90%-similar top results usually mean the same document was uploaded
    twice (or two versions of it exist), answering from an arbitrary one
    silently picks a version, so the caller should ask the user instead.
    """

    def body(h: SearchHit) -> str:
        # drop the "[Document: name]" contextual header - it differs per file
        # even when the underlying content is byte-identical
        text = h.text
        if text.startswith("[Document:"):
            text = text.split("\n", 1)[-1]
        return text

    top = hits[:5]
    for i, a in enumerate(top):
        for b in top[i + 1 :]:
            if a.file_id == b.file_id:
                continue
            if difflib.SequenceMatcher(None, body(a), body(b)).ratio() > threshold:
                return sorted({a.file_name, b.file_name})
    return None


def confidence_score(hits: list[SearchHit]) -> int:
    """0-100 from the best vector similarity among returned hits."""
    if not hits:
        return 0
    best = max(h.similarity for h in hits)
    return round(min(1.0, max(0.0, best)) * 100)
