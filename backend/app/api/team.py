"""Team analytics for department heads: how the department head's own department uses
the system (per-member queries/uploads, last activity). Admin sees it too,
scoped to their own department. Never crosses department lines.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.auth.rbac import ROLE_ADMIN, ROLE_HEAD
from app.database.db import get_db
from app.database.models import AuditLog, User

router = APIRouter(prefix="/api/team", tags=["team"])

_WINDOW_DAYS = 7
_QUERY_ACTIONS = ("chat.query", "search.query")


class TeamMember(BaseModel):
    id: int
    name: str
    role: str | None
    is_active: bool
    last_login: str | None
    queries_7d: int
    uploads_7d: int


class TeamStats(BaseModel):
    department: str
    members_total: int
    members_active_7d: int
    queries_7d: int
    uploads_7d: int
    members: list[TeamMember]


@router.get("/stats", response_model=TeamStats)
def team_stats(db: Annotated[Session, Depends(get_db)], user: CurrentUser) -> TeamStats:
    if user.role not in (ROLE_HEAD, ROLE_ADMIN):
        raise HTTPException(403, "Department Head or Admin access required")
    if not user.department:
        raise HTTPException(422, "Your account has no department set")

    members = db.scalars(
        select(User).where(User.department == user.department).order_by(User.full_name, User.email)
    ).all()
    ids = [m.id for m in members]
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=_WINDOW_DAYS)

    counts: dict[int, dict[str, int]] = {i: {"q": 0, "u": 0} for i in ids}
    if ids:
        rows = db.execute(
            select(AuditLog.user_id, AuditLog.action, func.count(AuditLog.id))
            .where(
                AuditLog.user_id.in_(ids),
                AuditLog.created_at >= since,
                AuditLog.action.in_((*_QUERY_ACTIONS, "file.upload")),
            )
            .group_by(AuditLog.user_id, AuditLog.action)
        ).all()
        for uid, action, n in rows:
            counts[uid]["u" if action == "file.upload" else "q"] += n

    def out(m: User) -> TeamMember:
        return TeamMember(
            id=m.id,
            name=m.full_name or m.email,
            role=m.role,
            is_active=m.is_active,
            last_login=m.last_login.isoformat() + "Z" if m.last_login else None,
            queries_7d=counts[m.id]["q"],
            uploads_7d=counts[m.id]["u"],
        )

    active_since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=_WINDOW_DAYS)
    return TeamStats(
        department=user.department,
        members_total=len(members),
        members_active_7d=sum(1 for m in members if m.last_login and m.last_login >= active_since),
        queries_7d=sum(c["q"] for c in counts.values()),
        uploads_7d=sum(c["u"] for c in counts.values()),
        members=[out(m) for m in members],
    )
