import re
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, status
from fastapi import File as FastAPIFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.auth.rbac import (
    ACCESS_DEPARTMENT,
    ACCESS_LEVELS,
    ACCESS_PRIVATE,
    ACCESS_PUBLIC,
    ROLE_ADMIN,
    ROLE_GUEST,
    ROLE_HEAD,
)
from app.config import get_settings
from app.database.db import get_db
from app.database.models import File
from app.parsers.auto_detect import validate_magic_bytes
from app.security.audit import log_action
from app.security.rate_limit import RateLimited
from app.security.storage import encrypt_bytes
from app.workers.file_processor import process_file

router = APIRouter(prefix="/api/upload", tags=["upload"])

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


class UploadResponse(BaseModel):
    file_id: int
    name: str
    index_status: str


@router.post("", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    _rl: RateLimited,
    file: UploadFile = FastAPIFile(...),
    access_level: str = Form(ACCESS_DEPARTMENT),
) -> UploadResponse:
    settings = get_settings()

    if access_level not in ACCESS_LEVELS:
        raise HTTPException(422, "access_level must be public, department or private")
    if user.role == ROLE_GUEST and access_level != ACCESS_PRIVATE:
        raise HTTPException(403, "Guests can only upload private files")
    if access_level == ACCESS_DEPARTMENT and not user.department:
        raise HTTPException(
            422, "Your account has no department - upload as private, or ask an admin to assign one"
        )
    # Only department heads/Admins publish to the whole company
    if access_level == ACCESS_PUBLIC and user.role not in (ROLE_ADMIN, ROLE_HEAD):
        raise HTTPException(403, "Only Admins and Department Heads can publish company-wide files")

    original_name = Path(file.filename or "").name
    ext = Path(original_name).suffix.lstrip(".").lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(422, f"File type .{ext or '?'} is not allowed")

    head = await file.read(16)
    if not head:
        raise HTTPException(422, "The file is empty")
    if not validate_magic_bytes(head, ext):
        raise HTTPException(422, "File content does not match its extension")

    max_bytes = settings.max_file_size_mb * 1024 * 1024
    size = len(head)
    dept = (user.department or "unassigned") if access_level != ACCESS_PRIVATE else f"user_{user.id}"
    safe_name = _SAFE_NAME.sub("_", original_name)[-120:]
    dest_dir = Path(settings.upload_dir) / _SAFE_NAME.sub("_", dept)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{uuid.uuid4().hex}_{safe_name}"

    # buffer in memory (<=50MB) so the blob can be encrypted at rest as one unit
    buf = bytearray(head)
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > max_bytes:
            raise HTTPException(413, f"File exceeds {settings.max_file_size_mb}MB limit")
        buf.extend(chunk)
    dest.write_bytes(encrypt_bytes(bytes(buf)))

    record = File(
        name=original_name,
        file_path=str(dest),
        file_type=ext,
        file_size_bytes=size,
        department=user.department if access_level != ACCESS_PRIVATE else None,
        owner_id=user.id,
        uploaded_by=user.id,
        access_level=access_level,
        is_public=access_level == ACCESS_PUBLIC,
        index_status="pending",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    log_action(
        db,
        user,
        "file.upload",
        "file",
        record.id,
        details={"name": original_name, "size": size, "access_level": access_level},
        ip_address=request.client.host if request.client else None,
    )
    process_file.delay(record.id)
    return UploadResponse(file_id=record.id, name=record.name, index_status=record.index_status)
