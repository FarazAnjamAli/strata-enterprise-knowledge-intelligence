"""RBAC: one canonical visibility rule, composed into every file/chunk query.

Roles (highest first): Admin, Department Head, Manager, Member, Guest.

Access levels (files.access_level):
  public      - visible to every department
  department  - visible inside the owning department
  private     - visible to the uploader only

Cross-department access comes from a file_access_permissions grant or an
approved, unexpired access_requests row for the requesting user.
"""

from datetime import UTC, datetime

from sqlalchemy import and_, exists, or_, select, true

from app.config import get_settings
from app.database.models import AccessRequest, File, FileAccessPermission, User

ROLE_ADMIN = "Admin"
ROLE_HEAD = "Department Head"
ROLE_MANAGER = "Manager"
ROLE_MEMBER = "Member"
ROLE_GUEST = "Guest"

ALL_ROLES = [ROLE_ADMIN, ROLE_HEAD, ROLE_MANAGER, ROLE_MEMBER, ROLE_GUEST]
APPROVER_ROLES = (ROLE_ADMIN, ROLE_HEAD)

ACCESS_PUBLIC = "public"
ACCESS_DEPARTMENT = "department"
ACCESS_PRIVATE = "private"
ACCESS_LEVELS = (ACCESS_PUBLIC, ACCESS_DEPARTMENT, ACCESS_PRIVATE)


def visible_files_filter(user: User):
    """SQLAlchemy boolean clause: which files this user may read."""
    if not get_settings().enable_rbac or user.role == ROLE_ADMIN:
        return true()

    own = or_(File.owner_id == user.id, File.uploaded_by == user.id)
    is_public = File.access_level == ACCESS_PUBLIC
    same_dept = and_(
        File.access_level == ACCESS_DEPARTMENT,
        File.department.is_not(None),
        File.department == user.department,
    )
    granted = exists().where(
        and_(
            FileAccessPermission.file_id == File.id,
            FileAccessPermission.can_read.is_(True),
            FileAccessPermission.department == user.department,
            or_(FileAccessPermission.role.is_(None), FileAccessPermission.role == user.role),
        )
    )
    approved_request = exists().where(
        and_(
            AccessRequest.file_id == File.id,
            AccessRequest.requester_id == user.id,
            AccessRequest.status == "approved",
            or_(
                AccessRequest.expires_at.is_(None),
                AccessRequest.expires_at > datetime.now(UTC).replace(tzinfo=None),
            ),
        )
    )
    # Guests only ever see what was explicitly shared with them
    if user.role == ROLE_GUEST:
        return or_(own, granted, approved_request)
    return or_(own, is_public, same_dept, granted, approved_request)


def can_read_file(db, user: User, file: File) -> bool:
    return db.scalar(select(File.id).where(File.id == file.id, visible_files_filter(user))) is not None
