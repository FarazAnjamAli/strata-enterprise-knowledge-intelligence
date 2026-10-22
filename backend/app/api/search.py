"""Raw hybrid-search endpoint for source browsing and relevance debugging.
Same RBAC path as chat."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.database.db import get_db
from app.rag.search import hybrid_search
from app.security.audit import log_action
from app.security.rate_limit import RateLimited
from app.security.sanitizer import sanitize_query

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=10, ge=1, le=50)


class SearchResult(BaseModel):
    chunk_id: int
    file_id: int
    file_name: str
    page: int | None
    section: str | None
    snippet: str
    score: float
    similarity: float


@router.post("", response_model=list[SearchResult])
def search(
    body: SearchRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    _rl: RateLimited,
) -> list[SearchResult]:
    q = sanitize_query(body.query)
    hits = hybrid_search(db, q, user, top_k=body.top_k)
    log_action(
        db,
        user,
        "search.query",
        "search",
        None,
        details={"query": q[:500], "results": len(hits)},
        ip_address=request.client.host if request.client else None,
    )
    return [
        SearchResult(
            chunk_id=h.chunk_id,
            file_id=h.file_id,
            file_name=h.file_name,
            page=h.page,
            section=h.section,
            snippet=h.text[:300],
            score=h.score,
            similarity=h.similarity,
        )
        for h in hits
    ]
