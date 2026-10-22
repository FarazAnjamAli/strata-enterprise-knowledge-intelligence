"""First-run setup: create the initial admin for local auth."""

import logging

from sqlalchemy import func, select

from app.auth.passwords import hash_password, password_problems
from app.auth.rbac import ROLE_ADMIN
from app.config import get_settings
from app.database.db import SessionLocal
from app.database.models import User

logger = logging.getLogger("strata.bootstrap")


def ensure_admin() -> None:
    s = get_settings()
    if s.auth_provider != "local" or not (s.bootstrap_admin_email and s.bootstrap_admin_password):
        return
    try:
        with SessionLocal() as db:
            if db.scalar(select(func.count(User.id))):
                return
            if problems := password_problems(s.bootstrap_admin_password):
                logger.error("BOOTSTRAP_ADMIN_PASSWORD rejected - needs %s", ", ".join(problems))
                return
            db.add(
                User(
                    email=s.bootstrap_admin_email.lower(),
                    full_name="Administrator",
                    password_hash=hash_password(s.bootstrap_admin_password),
                    role=ROLE_ADMIN,
                    is_active=True,
                )
            )
            db.commit()
            logger.info("bootstrap admin created: %s", s.bootstrap_admin_email)
    except Exception:
        logger.exception("bootstrap admin creation failed (database not migrated yet?)")
