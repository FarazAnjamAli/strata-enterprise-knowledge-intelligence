"""Admin-only endpoints: system stats, user management, audit trail and
LLM usage / cost reporting."""

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.types import Email
from app.auth.dependencies import AdminUser
from app.auth.passwords import hash_password, password_problems
from app.auth.rbac import ALL_ROLES, ROLE_ADMIN
from app.config import get_settings
from app.database.db import get_db
from app.database.models import AuditLog, File, FileChunk, LLMUsage, User
from app.security.audit import log_action

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _iso_utc(dt) -> str:
    """DB timestamps are naive UTC; mark them so browsers don't parse as local."""
    return dt.isoformat() + "Z"


class DeptCount(BaseModel):
    department: str
    count: int


class Stats(BaseModel):
    users_total: int
    users_active: int
    files_total: int
    files_ready: int
    files_failed: int
    files_in_progress: int
    chunks_total: int
    queries_24h: int
    uploads_7d: int
    users_by_department: list[DeptCount]


@router.get("/stats", response_model=Stats)
def stats(db: Annotated[Session, Depends(get_db)], admin: AdminUser) -> Stats:
    now = datetime.now(UTC).replace(tzinfo=None)

    def count(stmt) -> int:
        return db.scalar(stmt) or 0

    by_status = dict(
        db.execute(select(File.index_status, func.count(File.id)).group_by(File.index_status)).all()
    )
    by_dept = db.execute(
        select(User.department, func.count(User.id))
        .where(User.is_active.is_(True))
        .group_by(User.department)
        .order_by(func.count(User.id).desc())
    ).all()
    return Stats(
        users_total=count(select(func.count(User.id))),
        users_active=count(select(func.count(User.id)).where(User.is_active.is_(True))),
        files_total=sum(by_status.values()),
        files_ready=by_status.get("ready", 0),
        files_failed=by_status.get("failed", 0),
        files_in_progress=by_status.get("pending", 0) + by_status.get("processing", 0),
        chunks_total=count(select(func.count(FileChunk.id))),
        queries_24h=count(
            select(func.count(AuditLog.id)).where(
                AuditLog.action.in_(("chat.query", "search.query")),
                AuditLog.created_at > now - timedelta(hours=24),
            )
        ),
        uploads_7d=count(
            select(func.count(AuditLog.id)).where(
                AuditLog.action == "file.upload",
                AuditLog.created_at > now - timedelta(days=7),
            )
        ),
        users_by_department=[DeptCount(department=d or "Unassigned", count=n) for d, n in by_dept],
    )


class ActivityPoint(BaseModel):
    day: str  # YYYY-MM-DD
    queries: int
    uploads: int


@router.get("/activity", response_model=list[ActivityPoint])
def activity(
    db: Annotated[Session, Depends(get_db)],
    admin: AdminUser,
    days: Annotated[int, Query(ge=7, le=90)] = 14,
) -> list[ActivityPoint]:
    """Daily query/upload counts for the dashboard charts."""
    now = datetime.now(UTC).replace(tzinfo=None)
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    day_col = func.date(AuditLog.created_at)
    rows = db.execute(
        select(day_col, AuditLog.action, func.count(AuditLog.id))
        .where(
            AuditLog.created_at >= start,
            AuditLog.action.in_(("chat.query", "search.query", "file.upload")),
        )
        .group_by(day_col, AuditLog.action)
    ).all()
    buckets: dict[str, dict[str, int]] = {}
    for day, action, n in rows:
        key = str(day)
        b = buckets.setdefault(key, {"queries": 0, "uploads": 0})
        if action == "file.upload":
            b["uploads"] += n
        else:
            b["queries"] += n
    out = []
    for i in range(days):
        d = (start + timedelta(days=i)).date().isoformat()
        b = buckets.get(d, {"queries": 0, "uploads": 0})
        out.append(ActivityPoint(day=d, queries=b["queries"], uploads=b["uploads"]))
    return out


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str | None
    department: str | None
    role: str | None
    designation: str | None
    is_active: bool
    last_login: str | None
    created_at: str

    @classmethod
    def from_row(cls, u: User) -> "UserOut":
        return cls(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            department=u.department,
            role=u.role,
            designation=u.designation,
            is_active=u.is_active,
            last_login=_iso_utc(u.last_login) if u.last_login else None,
            created_at=_iso_utc(u.created_at),
        )


class UserUpdate(BaseModel):
    role: str | None = None
    department: str | None = Field(default=None, max_length=100)
    designation: str | None = Field(default=None, max_length=100)
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class UserCreate(BaseModel):
    email: Email
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=256)  # local auth only
    role: str = "Member"
    department: str | None = Field(default=None, max_length=100)
    designation: str | None = Field(default=None, max_length=100)


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    admin: AdminUser,
) -> UserOut:
    """Local auth: creates a sign-in-able account. Supabase: pre-creates the
    profile so role/department apply on the person's first sign-in."""
    if body.role not in ALL_ROLES:
        raise HTTPException(422, f"Role must be one of: {', '.join(ALL_ROLES)}")
    email = body.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(409, "A user with this email already exists")
    password_hash = None
    if get_settings().auth_provider == "local":
        if not body.password:
            raise HTTPException(422, "A password is required")
        if problems := password_problems(body.password):
            raise HTTPException(422, "Password needs " + ", ".join(problems))
        password_hash = hash_password(body.password)
    user = User(
        email=email,
        full_name=(body.full_name or "").strip() or None,
        password_hash=password_hash,
        role=body.role,
        department=(body.department or "").strip() or None,
        designation=(body.designation or "").strip() or None,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_action(
        db,
        admin,
        "admin.user_create",
        "user",
        user.id,
        details={"email": email, "role": body.role, "department": user.department},
        ip_address=request.client.host if request.client else None,
    )
    return UserOut.from_row(user)


class PasswordReset(BaseModel):
    password: str = Field(min_length=1, max_length=256)


@router.post("/users/{user_id}/password", status_code=204)
def reset_password(
    user_id: int,
    body: PasswordReset,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    admin: AdminUser,
) -> None:
    if get_settings().auth_provider != "local":
        raise HTTPException(422, "Passwords are managed by the identity provider")
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "User not found")
    if problems := password_problems(body.password):
        raise HTTPException(422, "Password needs " + ", ".join(problems))
    target.password_hash = hash_password(body.password)
    target.token_version = (target.token_version or 0) + 1  # end their sessions
    db.commit()
    log_action(
        db,
        admin,
        "admin.password_reset",
        "user",
        target.id,
        ip_address=request.client.host if request.client else None,
    )


@router.get("/users", response_model=list[UserOut])
def list_users(db: Annotated[Session, Depends(get_db)], admin: AdminUser) -> list[UserOut]:
    rows = db.scalars(select(User).order_by(User.created_at.desc()).limit(500)).all()
    return [UserOut.from_row(u) for u in rows]


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    admin: AdminUser,
) -> UserOut:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "User not found")

    # exclude_unset (not exclude_none) so department/full_name can be cleared;
    # empty string means "clear", RBAC must never see a phantom '' department
    changes = body.model_dump(exclude_unset=True)
    for field in ("department", "designation", "full_name"):
        if field in changes and changes[field] is not None and not changes[field].strip():
            changes[field] = None
    if "role" in changes and changes["role"] not in ALL_ROLES:
        raise HTTPException(422, f"Role must be one of: {', '.join(ALL_ROLES)}")
    if "is_active" in changes and changes["is_active"] is None:
        del changes["is_active"]
    if target.id == admin.id and (
        changes.get("is_active") is False or ("role" in changes and changes["role"] != ROLE_ADMIN)
    ):
        raise HTTPException(422, "You can't deactivate or demote your own admin account")
    for field, value in changes.items():
        setattr(target, field, value)
    if changes.get("is_active") is False:
        target.token_version = (target.token_version or 0) + 1
    db.commit()
    db.refresh(target)
    log_action(
        db,
        admin,
        "admin.user_update",
        "user",
        target.id,
        details=changes,
        ip_address=request.client.host if request.client else None,
    )
    return UserOut.from_row(target)


class AuditLogOut(BaseModel):
    id: int
    user_id: int | None
    user_email: str | None
    action: str | None
    resource_type: str | None
    resource_id: int | None
    details: dict | None
    ip_address: str | None
    created_at: str


class AuditLogPage(BaseModel):
    total: int
    items: list[AuditLogOut]


def _audit_conditions(
    user_id: int | None, action: str | None, date_from: str | None, date_to: str | None
) -> list:
    def parse_day(value: str, label: str) -> datetime:
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(422, f"{label} must be YYYY-MM-DD")

    conditions = []
    if date_from:
        conditions.append(AuditLog.created_at >= parse_day(date_from, "date_from"))
    if date_to:
        conditions.append(AuditLog.created_at < parse_day(date_to, "date_to") + timedelta(days=1))
    if user_id is not None:
        conditions.append(AuditLog.user_id == user_id)
    if action:
        literal = action.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(AuditLog.action.like(f"{literal}%", escape="\\"))
    return conditions


@router.get("/audit-logs", response_model=AuditLogPage)
def list_audit_logs(
    db: Annotated[Session, Depends(get_db)],
    admin: AdminUser,
    user_id: int | None = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    date_from: Annotated[str | None, Query(description="YYYY-MM-DD")] = None,
    date_to: Annotated[str | None, Query(description="YYYY-MM-DD")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogPage:
    conditions = _audit_conditions(user_id, action, date_from, date_to)
    total = db.scalar(select(func.count(AuditLog.id)).where(*conditions)) or 0
    rows = db.execute(
        select(AuditLog, User.email)
        .join(User, User.id == AuditLog.user_id, isouter=True)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return AuditLogPage(
        total=total,
        items=[
            AuditLogOut(
                id=log.id,
                user_id=log.user_id,
                user_email=email,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=log.resource_id,
                details=log.details,
                ip_address=log.ip_address,
                created_at=_iso_utc(log.created_at),
            )
            for log, email in rows
        ],
    )


_EXPORT_CAP = 50_000  # ponytail: hard row cap; stream in date batches if ever exceeded


@router.get("/audit-logs/export")
def export_audit_logs(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    admin: AdminUser,
    user_id: int | None = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    date_from: Annotated[str | None, Query(description="YYYY-MM-DD")] = None,
    date_to: Annotated[str | None, Query(description="YYYY-MM-DD")] = None,
) -> StreamingResponse:
    """CSV export of the audit trail, honoring the same filters as the list view."""
    conditions = _audit_conditions(user_id, action, date_from, date_to)
    rows = db.execute(
        select(AuditLog, User.email)
        .join(User, User.id == AuditLog.user_id, isouter=True)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc())
        .limit(_EXPORT_CAP)
    ).all()
    log_action(
        db,
        admin,
        "admin.audit_export",
        details={
            "rows": len(rows),
            "user_id": user_id,
            "action": action,
            "date_from": date_from,
            "date_to": date_to,
        },
        ip_address=request.client.host if request.client else None,
    )

    def gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            [
                "id",
                "timestamp_utc",
                "user_id",
                "user_email",
                "action",
                "resource_type",
                "resource_id",
                "ip_address",
                "details",
            ]
        )
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()
        for log, email in rows:
            w.writerow(
                [
                    log.id,
                    _iso_utc(log.created_at),
                    log.user_id,
                    email,
                    log.action,
                    log.resource_type,
                    log.resource_id,
                    log.ip_address,
                    json.dumps(log.details) if log.details else "",
                ]
            )
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()

    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return StreamingResponse(
        gen(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=audit-logs-{stamp}.csv"},
    )


class TierUsage(BaseModel):
    tier: str
    calls: int
    failures: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    avg_latency_ms: int


class UsageDay(BaseModel):
    day: str
    local: int
    free: int
    paid: int


class LLMUsageReport(BaseModel):
    days: int
    tiers: list[TierUsage]
    daily: list[UsageDay]
    month_paid_spend_usd: float
    monthly_budget_usd: float


@router.get("/llm-usage", response_model=LLMUsageReport)
def llm_usage(
    db: Annotated[Session, Depends(get_db)],
    admin: AdminUser,
    days: Annotated[int, Query(ge=1, le=90)] = 30,
) -> LLMUsageReport:
    """Which tier is answering, how often it fails, and what it costs."""
    from app.llm import usage as llm_usage_mod

    now = datetime.now(UTC).replace(tzinfo=None)
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.execute(
        select(
            LLMUsage.tier,
            func.count(LLMUsage.id),
            func.count(LLMUsage.id).filter(LLMUsage.success.is_(False)),
            func.coalesce(func.sum(LLMUsage.prompt_tokens), 0),
            func.coalesce(func.sum(LLMUsage.completion_tokens), 0),
            func.coalesce(func.sum(LLMUsage.cost_usd), 0.0),
            func.coalesce(func.avg(LLMUsage.latency_ms).filter(LLMUsage.success.is_(True)), 0),
        )
        .where(LLMUsage.created_at >= start)
        .group_by(LLMUsage.tier)
    ).all()
    by_tier = {r[0]: r for r in rows}
    tiers = []
    for t in ("local", "free", "paid"):
        r = by_tier.get(t)
        tiers.append(
            TierUsage(
                tier=t,
                calls=r[1] if r else 0,
                failures=r[2] if r else 0,
                prompt_tokens=int(r[3]) if r else 0,
                completion_tokens=int(r[4]) if r else 0,
                cost_usd=round(float(r[5]), 4) if r else 0.0,
                avg_latency_ms=int(r[6]) if r else 0,
            )
        )
    day_col = func.date(LLMUsage.created_at)
    daily_rows = db.execute(
        select(day_col, LLMUsage.tier, func.count(LLMUsage.id))
        .where(LLMUsage.created_at >= start, LLMUsage.success.is_(True))
        .group_by(day_col, LLMUsage.tier)
    ).all()
    buckets: dict[str, dict[str, int]] = {}
    for day, tier, n in daily_rows:
        buckets.setdefault(str(day), {})[tier] = n
    daily = []
    for i in range(days):
        d = (start + timedelta(days=i)).date().isoformat()
        b = buckets.get(d, {})
        daily.append(UsageDay(day=d, local=b.get("local", 0), free=b.get("free", 0), paid=b.get("paid", 0)))
    spend = llm_usage_mod.paid_month_spend()
    return LLMUsageReport(
        days=days,
        tiers=tiers,
        daily=daily,
        month_paid_spend_usd=round(spend, 4) if spend != float("inf") else 0.0,
        monthly_budget_usd=get_settings().paid_llm_monthly_budget_usd,
    )
