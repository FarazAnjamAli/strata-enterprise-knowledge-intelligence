"""Cross-department access: request -> department head/Admin approval -> RBAC grant.

The grant itself is just an approved `access_requests` row, the canonical
`visible_files_filter` already honors those, so approving a request is the
only write needed to open access. Standing rules (`department_access_rules`)
auto-approve matching requests at request time, before any human sees them.

Decisions (per the build reference): approve once (time-boxed), approve
recurring (no expiry), deny. Requests are asynchronous, the chat flow never
blocks on an approval.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.auth.rbac import (
    ACCESS_DEPARTMENT,
    ALL_ROLES,
    ROLE_ADMIN,
    ROLE_HEAD,
    visible_files_filter,
)
from app.database.db import get_db
from app.database.models import AccessRequest, DepartmentAccessRule, File, User
from app.integrations import webhooks
from app.security.audit import log_action

router = APIRouter(prefix="/api/access", tags=["access"])

_ONCE_GRANT_HOURS = 24  # "approve once" default validity


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)  # DB stores naive UTC


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ------------------------------ catalog ----------------------------------


class CatalogFile(BaseModel):
    id: int
    name: str
    file_type: str | None
    department: str | None
    my_request_status: str | None  # pending/approved/denied for this user


@router.get("/catalog", response_model=list[CatalogFile])
def catalog(db: Annotated[Session, Depends(get_db)], user: CurrentUser) -> list[CatalogFile]:
    """Department-level files the user can NOT read: name + owning department
    only (metadata-level discovery so there is something to request). Private
    files are never listed."""
    rows = db.scalars(
        select(File)
        .where(
            File.access_level == ACCESS_DEPARTMENT,
            File.index_status == "ready",
            ~visible_files_filter(user),
        )
        .order_by(File.department, File.name)
        .limit(500)
    ).all()
    latest: dict[int, str] = {}
    for req in db.scalars(
        select(AccessRequest)
        .where(AccessRequest.requester_id == user.id)
        .order_by(AccessRequest.requested_at)
    ):
        latest[req.file_id] = req.status or "pending"
    return [
        CatalogFile(
            id=f.id,
            name=f.name,
            file_type=f.file_type,
            department=f.department,
            my_request_status=latest.get(f.id),
        )
        for f in rows
    ]


# ------------------------------ requests ---------------------------------


class RequestCreate(BaseModel):
    file_id: int


class RequestOut(BaseModel):
    id: int
    file_id: int
    file_name: str | None
    department: str | None
    requester_id: int | None
    requester_email: str | None
    status: str | None
    is_recurring: bool
    requested_at: str
    expires_at: str | None


def _request_out(req: AccessRequest, file: File | None, requester: User | None) -> RequestOut:
    return RequestOut(
        id=req.id,
        file_id=req.file_id,
        file_name=file.name if file else None,
        department=file.department if file else None,
        requester_id=req.requester_id,
        requester_email=requester.email if requester else None,
        status=req.status,
        is_recurring=req.is_recurring,
        requested_at=_iso(req.requested_at) or "",
        expires_at=_iso(req.expires_at),
    )


def _standing_rule_match(db: Session, user: User, file: File) -> DepartmentAccessRule | None:
    return db.scalar(
        select(DepartmentAccessRule).where(
            DepartmentAccessRule.is_active.is_(True),
            DepartmentAccessRule.action == "auto_approve",
            DepartmentAccessRule.department == file.department,
            (DepartmentAccessRule.source_role.is_(None)) | (DepartmentAccessRule.source_role == user.role),
            (DepartmentAccessRule.target_file_type.is_(None))
            | (DepartmentAccessRule.target_file_type == file.file_type),
        )
    )


@router.post("", response_model=RequestOut, status_code=201)
def create_request(
    body: RequestCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> RequestOut:
    file = db.get(File, body.file_id)
    # only department-level files are requestable; pretend private ones don't exist
    if file is None or file.access_level != ACCESS_DEPARTMENT:
        raise HTTPException(404, "File not found")
    if db.scalar(select(File.id).where(File.id == file.id, visible_files_filter(user))):
        raise HTTPException(422, "You already have access to this file")
    dup = db.scalar(
        select(AccessRequest).where(
            AccessRequest.file_id == file.id,
            AccessRequest.requester_id == user.id,
            AccessRequest.status == "pending",
        )
    )
    if dup:
        return _request_out(dup, file, user)

    req = AccessRequest(requester_id=user.id, file_id=file.id, status="pending")
    rule = _standing_rule_match(db, user, file)
    if rule:
        req.status = "approved"
        req.approver_id = rule.created_by
        req.approved_at = _now()
        if rule.auto_approve_after_hours:
            req.expires_at = _now() + timedelta(hours=rule.auto_approve_after_hours)
    db.add(req)
    db.commit()
    db.refresh(req)

    log_action(
        db,
        user,
        "access.request",
        "file",
        file.id,
        details={"request_id": req.id, "status": req.status, "standing_rule": rule.id if rule else None},
        ip_address=_ip(request),
    )
    if not rule:
        webhooks.notify(
            "access_request.created",
            {
                "request_id": req.id,
                "file": file.name,
                "department": file.department,
                "requester": user.email,
            },
        )
    return _request_out(req, file, user)


def _approver_scope(user: User):
    """department heads see requests for their department's files; Admin sees all."""
    if user.role == ROLE_ADMIN:
        return None
    if user.role == ROLE_HEAD and user.department:
        return user.department
    raise HTTPException(403, "Department Head or Admin access required")


@router.get("", response_model=list[RequestOut])
def list_requests(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    box: Annotated[str, Query(pattern="^(mine|inbox)$")] = "mine",
) -> list[RequestOut]:
    stmt = (
        select(AccessRequest, File, User)
        .join(File, File.id == AccessRequest.file_id)
        .join(User, User.id == AccessRequest.requester_id, isouter=True)
        .order_by(AccessRequest.requested_at.desc())
        .limit(200)
    )
    if box == "mine":
        stmt = stmt.where(AccessRequest.requester_id == user.id)
    else:
        dept = _approver_scope(user)
        if dept is not None:
            stmt = stmt.where(File.department == dept)
    return [_request_out(r, f, u) for r, f, u in db.execute(stmt).all()]


class Decision(BaseModel):
    decision: str = Field(pattern="^(approve_once|approve_recurring|deny)$")
    expires_hours: int | None = Field(default=None, ge=1, le=24 * 90)


@router.post("/{request_id}/decide", response_model=RequestOut)
def decide(
    request_id: int,
    body: Decision,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> RequestOut:
    req = db.get(AccessRequest, request_id)
    if req is None:
        raise HTTPException(404, "Request not found")
    file = db.get(File, req.file_id)
    dept = _approver_scope(user)
    if dept is not None and (file is None or file.department != dept):
        raise HTTPException(403, "This request belongs to another department")
    if req.status != "pending":
        raise HTTPException(422, f"Request was already {req.status}")

    if body.decision == "deny":
        req.status = "denied"
    else:
        req.status = "approved"
        req.is_recurring = body.decision == "approve_recurring"
        req.expires_at = (
            None if req.is_recurring else _now() + timedelta(hours=body.expires_hours or _ONCE_GRANT_HOURS)
        )
    req.approver_id = user.id
    req.approved_at = _now()
    db.commit()
    db.refresh(req)

    requester = db.get(User, req.requester_id) if req.requester_id else None
    log_action(
        db,
        user,
        f"access.{req.status}",
        "file",
        req.file_id,
        details={
            "request_id": req.id,
            "decision": body.decision,
            "requester": requester.email if requester else None,
        },
        ip_address=_ip(request),
    )
    webhooks.notify(
        "access_request.decided",
        {
            "request_id": req.id,
            "status": req.status,
            "file": file.name if file else None,
            "requester": requester.email if requester else None,
            "decided_by": user.email,
        },
    )
    return _request_out(req, file, requester)


# ---------------------------- standing rules ------------------------------


class RuleCreate(BaseModel):
    rule_name: str = Field(max_length=255)
    source_role: str | None = None  # None = any role
    target_file_type: str | None = Field(default=None, max_length=100)  # None = any type
    grant_hours: int | None = Field(default=None, ge=1, le=24 * 365)  # None = no expiry


class RuleOut(BaseModel):
    id: int
    department: str | None
    rule_name: str | None
    source_role: str | None
    target_file_type: str | None
    grant_hours: int | None
    is_active: bool


def _rule_out(r: DepartmentAccessRule) -> RuleOut:
    return RuleOut(
        id=r.id,
        department=r.department,
        rule_name=r.rule_name,
        source_role=r.source_role,
        target_file_type=r.target_file_type,
        grant_hours=r.auto_approve_after_hours,
        is_active=r.is_active,
    )


@router.get("/rules", response_model=list[RuleOut])
def list_rules(db: Annotated[Session, Depends(get_db)], user: CurrentUser) -> list[RuleOut]:
    dept = _approver_scope(user)
    stmt = select(DepartmentAccessRule).where(DepartmentAccessRule.is_active.is_(True))
    if dept is not None:
        stmt = stmt.where(DepartmentAccessRule.department == dept)
    return [_rule_out(r) for r in db.scalars(stmt.order_by(DepartmentAccessRule.id))]


@router.post("/rules", response_model=RuleOut, status_code=201)
def create_rule(
    body: RuleCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> RuleOut:
    dept = _approver_scope(user)
    if dept is None:  # Admin still needs a department for the rule: their own
        dept = user.department
        if not dept:
            raise HTTPException(422, "Set your department before creating rules")
    if body.source_role is not None and body.source_role not in ALL_ROLES:
        raise HTTPException(422, f"source_role must be one of: {', '.join(ALL_ROLES)}")
    rule = DepartmentAccessRule(
        department=dept,
        created_by=user.id,
        rule_name=body.rule_name,
        source_role=body.source_role,
        target_file_type=(body.target_file_type or None),
        action="auto_approve",
        auto_approve_after_hours=body.grant_hours,
        is_active=True,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    log_action(
        db,
        user,
        "access.rule_create",
        "department_access_rule",
        rule.id,
        details={"name": rule.rule_name, "role": rule.source_role, "file_type": rule.target_file_type},
        ip_address=_ip(request),
    )
    return _rule_out(rule)


@router.delete("/rules/{rule_id}", status_code=204)
def delete_rule(
    rule_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> None:
    rule = db.get(DepartmentAccessRule, rule_id)
    if rule is None or not rule.is_active:
        raise HTTPException(404, "Rule not found")
    dept = _approver_scope(user)
    if dept is not None and rule.department != dept:
        raise HTTPException(403, "This rule belongs to another department")
    rule.is_active = False  # soft delete keeps the audit story coherent
    db.commit()
    log_action(
        db,
        user,
        "access.rule_delete",
        "department_access_rule",
        rule_id,
        details={"name": rule.rule_name},
        ip_address=_ip(request),
    )
