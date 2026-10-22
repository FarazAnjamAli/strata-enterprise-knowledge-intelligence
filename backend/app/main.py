"""FastAPI application factory."""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import access, admin, auth, chat, files, health, image, search, system, team, upload
from app.bootstrap import ensure_admin
from app.config import get_settings
from app.logging_config import configure_logging

logger = logging.getLogger("strata.http")


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    s = get_settings()
    if problems := s.validate_runtime():
        for p in problems:
            logger.critical("configuration error: %s", p)
        raise RuntimeError("invalid configuration: " + "; ".join(problems))
    ensure_admin()
    logger.info(
        "%s %s started (%s, auth=%s, tiers=%s)",
        s.app_name,
        s.app_version,
        s.environment,
        s.auth_provider,
        ",".join(s.tier_order),
    )
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=f"{s.app_name} API",
        version=s.app_version,
        description="Three-tier, on-prem-first retrieval-augmented generation.",
        docs_url="/docs" if not s.is_production else None,
        redoc_url=None,
        openapi_url="/openapi.json" if not s.is_production else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Strata-CSRF", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path not in ("/health", "/health/ready"):
            logger.info(
                "%s %s %s %dms",
                request.method,
                request.url.path,
                response.status_code,
                int((time.perf_counter() - started) * 1000),
                extra={"request_id": rid},
            )
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return JSONResponse(
            {"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None)
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        detail = [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]
        return JSONResponse({"detail": detail}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        # never leak stack traces to clients
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    for module in (health, system, auth, upload, files, search, chat, image, access, team, admin):
        app.include_router(module.router)
    return app


app = create_app()
