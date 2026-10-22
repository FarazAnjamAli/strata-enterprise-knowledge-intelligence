import logging

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.models import AuditLog, User

logger = logging.getLogger("strata.audit")


def log_action(
    db: Session,
    user: User | None,
    action: str,
    resource_type: str | None = None,
    resource_id: int | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """Write an audit row. Never raises, auditing must not break requests -
    but failures are logged loudly for the ops trail."""
    if not get_settings().enable_audit_logging:
        return
    try:
        db.add(
            AuditLog(
                user_id=user.id if user else None,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                ip_address=ip_address,
            )
        )
        db.commit()
    except Exception:
        logger.exception("audit write failed: action=%s user=%s", action, user and user.id)
        db.rollback()
