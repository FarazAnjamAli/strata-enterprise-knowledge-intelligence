"""Celery beat task: requeue files stuck in pending/processing.

task_acks_late + task_reject_on_worker_lost (celery_app.py) already redeliver
when a worker dies mid-task; this sweeper is the backstop for tasks that were
never delivered at all (Redis flushed, enqueue lost, stack rebuilt).
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select

from app.database.db import SessionLocal
from app.database.models import File
from app.workers.celery_app import celery_app
from app.workers.file_processor import process_file

logger = logging.getLogger("strata.cleanup")

# 'processing' means a worker really started it, give slow parses (big OCR
# PDFs) ample room before assuming the task is gone. 'pending' just sits in
# the queue, so a shorter window is safe.
_PENDING_STUCK_AFTER = timedelta(minutes=30)
_PROCESSING_STUCK_AFTER = timedelta(hours=2)


@celery_app.task(name="strata.requeue_stuck_files")
def requeue_stuck_files() -> int:
    # ponytail: a >2h-but-alive task can still get a duplicate; add a
    # heartbeat column if genuinely hours-long files ever become a thing.
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        stuck = db.scalars(
            select(File).where(
                or_(
                    and_(
                        File.index_status == "pending",
                        File.updated_at < now - _PENDING_STUCK_AFTER,
                    ),
                    and_(
                        File.index_status == "processing",
                        File.updated_at < now - _PROCESSING_STUCK_AFTER,
                    ),
                )
            )
        ).all()
        ids = [f.id for f in stuck]
        for f in stuck:
            f.index_status = "pending"
            # explicit bump: assigning identical values emits no UPDATE, and
            # then the next sweep would requeue the same file again
            f.updated_at = now
        db.commit()
    for file_id in ids:
        process_file.delay(file_id)
    if ids:
        logger.info("requeued stuck files: %s", ids)
    return len(ids)
