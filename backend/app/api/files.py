import mimetypes
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.auth.rbac import (
    ACCESS_DEPARTMENT,
    ACCESS_LEVELS,
    ACCESS_PUBLIC,
    ROLE_ADMIN,
    ROLE_HEAD,
    visible_files_filter,
)
from app.database.db import get_db
from app.database.models import File
from app.security.audit import log_action
from app.security.storage import DecryptionError, read_decrypted

router = APIRouter(prefix="/api/files", tags=["files"])


class FileOut(BaseModel):
    id: int
    name: str
    file_type: str | None
    file_size_bytes: int | None
    department: str | None
    access_level: str | None
    index_status: str
    index_error: str | None
    created_at: str
    owner_id: int | None
    chunk_count: int

    @classmethod
    def from_row(cls, f: File) -> "FileOut":
        return cls(
            id=f.id,
            name=f.name,
            file_type=f.file_type,
            file_size_bytes=f.file_size_bytes,
            department=f.department,
            access_level=f.access_level,
            index_status=f.index_status,
            index_error=f.index_error,
            # naive UTC in the DB; the Z keeps browsers from parsing as local
            created_at=f.created_at.isoformat() + "Z",
            owner_id=f.owner_id,
            chunk_count=f.chunk_count or 0,
        )


@router.get("", response_model=list[FileOut])
def list_files(
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> list[FileOut]:
    rows = db.scalars(
        select(File).where(visible_files_filter(user)).order_by(File.created_at.desc()).limit(limit)
    ).all()
    return [FileOut.from_row(f) for f in rows]


@router.get("/{file_id}", response_model=FileOut)
def get_file(
    file_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> FileOut:
    row = db.scalar(select(File).where(File.id == file_id, visible_files_filter(user)))
    if row is None:
        # 404 (not 403) so existence of other departments' files isn't leaked
        raise HTTPException(404, "File not found")
    log_action(
        db, user, "file.view", "file", row.id, ip_address=request.client.host if request.client else None
    )
    return FileOut.from_row(row)


@router.get("/{file_id}/download")
def download_file(
    file_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> Response:
    """Serve the original document (decrypted) for citation click-through."""
    row = db.scalar(select(File).where(File.id == file_id, visible_files_filter(user)))
    if row is None:
        raise HTTPException(404, "File not found")
    path = Path(row.file_path or "")
    if not path.is_file():
        raise HTTPException(404, "Stored file is missing")
    try:
        data = read_decrypted(path)
    except DecryptionError:
        raise HTTPException(500, "File cannot be decrypted with the configured key")
    log_action(
        db, user, "file.download", "file", row.id, ip_address=request.client.host if request.client else None
    )
    media = mimetypes.guess_type(row.name)[0] or "application/octet-stream"
    return Response(
        data,
        media_type=media,
        # inline lets PDFs/images open in the browser; filename* handles non-ASCII
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(row.name)}"},
    )


@router.delete("/{file_id}", status_code=204)
def delete_file(
    file_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> None:
    """Remove a file, its chunks (FK cascade) and the stored blob.

    Deletion rules:
      - Admin: any file, including public.
      - department head: any non-public file in their own department.
      - Everyone: their own private uploads.
    """
    row = db.scalar(select(File).where(File.id == file_id))
    if row is None:
        raise HTTPException(404, "File not found")

    is_owner = row.owner_id == user.id or row.uploaded_by == user.id
    is_admin = user.role == ROLE_ADMIN
    is_dept_head = (
        user.role == ROLE_HEAD
        and row.access_level != ACCESS_PUBLIC
        and row.department == user.department
        and row.department is not None
    )
    # owners may always remove their own upload; admins anything;
    # department heads any non-public file in their department
    if not (is_admin or is_owner or is_dept_head):
        raise HTTPException(403, "You don't have permission to delete this file")

    name, stored_path = row.name, row.file_path
    db.delete(row)
    db.commit()
    if stored_path:
        Path(stored_path).unlink(missing_ok=True)
    log_action(
        db,
        user,
        "file.delete",
        "file",
        file_id,
        details={"name": name},
        ip_address=request.client.host if request.client else None,
    )


class AccessUpdate(BaseModel):
    access_level: str


@router.patch("/{file_id}", response_model=FileOut)
def update_access(
    file_id: int,
    body: AccessUpdate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> FileOut:
    """Admin: any file. department head: files of their own department (or their own)."""
    if body.access_level not in ACCESS_LEVELS:
        raise HTTPException(422, "access_level must be public, department or private")
    row = db.scalar(select(File).where(File.id == file_id))
    if row is None:
        raise HTTPException(404, "File not found")

    is_admin = user.role == ROLE_ADMIN
    is_dept_head = user.role == ROLE_HEAD and (row.department == user.department or row.owner_id == user.id)
    if not (is_admin or is_dept_head):
        raise HTTPException(403, "Only an Admin or the owning Department Head can change access")

    row.access_level = body.access_level
    row.is_public = body.access_level == ACCESS_PUBLIC
    if body.access_level in (ACCESS_DEPARTMENT, ACCESS_PUBLIC) and not row.department:
        # a private file being opened up adopts the actor's department,
        # so department/public files always show which team owns them
        row.department = user.department
    db.commit()
    db.refresh(row)
    log_action(
        db,
        user,
        "file.access_change",
        "file",
        row.id,
        details={"access_level": body.access_level},
        ip_address=request.client.host if request.client else None,
    )
    return FileOut.from_row(row)


@router.post("/{file_id}/reindex", response_model=FileOut, status_code=202)
def reindex_file(
    file_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> FileOut:
    """Re-run parsing/embedding (e.g. after a failure or a model change)."""
    from app.workers.file_processor import process_file

    row = db.scalar(select(File).where(File.id == file_id, visible_files_filter(user)))
    if row is None:
        raise HTTPException(404, "File not found")
    if not (
        user.role == ROLE_ADMIN
        or row.owner_id == user.id
        or (user.role == ROLE_HEAD and row.department == user.department)
    ):
        raise HTTPException(403, "You can't reindex this file")
    row.index_status, row.index_error = "pending", None
    db.commit()
    db.refresh(row)
    process_file.delay(row.id)
    log_action(
        db, user, "file.reindex", "file", row.id, ip_address=request.client.host if request.client else None
    )
    return FileOut.from_row(row)
