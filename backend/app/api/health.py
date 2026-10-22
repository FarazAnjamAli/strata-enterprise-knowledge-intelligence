import redis as redis_lib
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.config import get_settings
from app.database.db import engine

router = APIRouter(tags=["health"])


@router.get("/health")
def liveness() -> dict:
    s = get_settings()
    return {"status": "ok", "app": s.app_name, "version": s.app_version}


@router.get("/health/ready")
def readiness(response: Response) -> dict:
    checks = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "unreachable"
    try:
        r = redis_lib.from_url(get_settings().redis_url, socket_connect_timeout=2)
        r.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unreachable"

    healthy = all(v == "ok" for v in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "degraded", "checks": checks}
