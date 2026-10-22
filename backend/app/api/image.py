"""Diagram generation for the chat /image command, plus its audit store.

Off unless IMAGE_GENERATION_ENABLED=true and GEMINI_API_KEY is set, because
the prompt leaves the network. Generated images are stored encrypted at rest
and listed for their creator (Admins see everyone's).
"""

import base64
import logging
import mimetypes
import uuid
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.auth.rbac import ROLE_ADMIN, ROLE_HEAD
from app.config import get_settings
from app.database.db import get_db
from app.database.models import GeneratedImage, User
from app.security.audit import log_action
from app.security.masking import mask_financial_data
from app.security.rate_limit import RateLimited
from app.security.sanitizer import sanitize_query
from app.security.storage import DecryptionError, encrypt_bytes, read_decrypted

logger = logging.getLogger("strata.image")

router = APIRouter(prefix="/api/image", tags=["image"])


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


# /image is a documentation tool, not a toy: every prompt is wrapped so the
# model renders a diagram/workflow in the brand style, never photos or scenes
_DIAGRAM_STYLE = (
    "Create a clean, professional DIAGRAM for internal documentation: a "
    "flowchart, process workflow, org chart, architecture or technical "
    "illustration. Minimal style on a white background, thin black lines, "
    "clearly labeled boxes and arrows, a single lime-green (#C6FF00) accent. "
    "Never a photo, portrait or artistic scene. The diagram to draw:\n"
)


class ImageResponse(BaseModel):
    id: int | None  # DB row id, for the chat download link (None if not saved)
    image_base64: str
    mime_type: str
    text: str | None  # any caption the model returned alongside the image


class _Generated:
    """Provider result before it's persisted."""

    def __init__(self, data: bytes, mime_type: str, provider: str, text: str | None):
        self.data = data
        self.mime_type = mime_type
        self.provider = provider
        self.text = text


def _gemini(prompt: str) -> _Generated:
    settings = get_settings()
    resp = httpx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_image_model}:generateContent",
        headers={"x-goog-api-key": settings.gemini_api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        },
        timeout=settings.gemini_timeout,
    )
    resp.raise_for_status()
    parts = resp.json()["candidates"][0]["content"]["parts"]
    image = next((p["inlineData"] for p in parts if "inlineData" in p), None)
    if image is None:
        raise ValueError("no image part in response")
    return _Generated(
        data=base64.b64decode(image["data"]),
        mime_type=image.get("mimeType", "image/png"),
        provider=f"gemini/{settings.gemini_image_model}",
        text=next((p["text"] for p in parts if "text" in p), None),
    )


@router.post("", response_model=ImageResponse)
def generate_image(
    body: ImageRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    _rl: RateLimited,
) -> ImageResponse:
    settings = get_settings()
    if not (settings.image_generation_enabled and settings.gemini_api_key):
        raise HTTPException(404, "Diagram generation is not enabled on this server")
    prompt = sanitize_query(body.prompt)
    if not prompt:
        raise HTTPException(422, "Prompt is empty after sanitization")
    try:
        result = _gemini(_DIAGRAM_STYLE + mask_financial_data(prompt))
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        logger.error("image generation failed: %s", exc)
        raise HTTPException(502, "Diagram generation failed - try again in a minute.")

    # save encrypted at rest so the admin/department head viewer and re-download can serve
    # it later; a storage failure must not lose the generated picture to the user
    ext = mimetypes.guess_extension(result.mime_type) or ".png"
    row_id: int | None = None
    try:
        dest_dir = Path(settings.upload_dir) / "generated"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{uuid.uuid4().hex}{ext}"
        dest.write_bytes(encrypt_bytes(result.data))
        row = GeneratedImage(
            user_id=user.id,
            department=user.department,
            prompt=prompt[:2000],
            provider=result.provider,
            mime_type=result.mime_type,
            file_path=str(dest),
            file_size_bytes=len(result.data),
        )
        db.add(row)
        db.commit()
        row_id = row.id
    except OSError as exc:
        logger.error("could not persist generated image: %s", exc)

    log_action(
        db,
        user,
        "chat.image",
        "image",
        row_id,
        details={"prompt": prompt[:500], "provider": result.provider},
        ip_address=request.client.host if request.client else None,
    )
    return ImageResponse(
        id=row_id,
        image_base64=base64.b64encode(result.data).decode(),
        mime_type=result.mime_type,
        text=result.text,
    )


class GeneratedImageOut(BaseModel):
    id: int
    user_id: int | None
    user_email: str | None
    user_name: str | None
    department: str | None
    prompt: str
    provider: str | None
    mime_type: str | None
    created_at: str


class ImageHistoryPage(BaseModel):
    total: int
    scope: str  # "all" | "department" | "mine", so the UI can label the section
    items: list[GeneratedImageOut]


def _history_scope(user: User, requested: str | None = None):
    """(condition, scope-label) for the listing query.

    Any user can pass ?scope=mine to force their own diagrams only, the
    per-user dashboard section uses this even for Admins. Otherwise the
    default is by role: Admin -> everyone; department head and everyone else -> their
    own (department heads no longer see the whole department here)."""
    if requested == "mine":
        return GeneratedImage.user_id == user.id, "mine"
    if user.role == ROLE_ADMIN:
        return True, "all"
    return GeneratedImage.user_id == user.id, "mine"


@router.get("/history", response_model=ImageHistoryPage)
def image_history(
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    scope: Annotated[str | None, Query()] = None,
) -> ImageHistoryPage:
    condition, scope = _history_scope(user, scope)
    total = db.scalar(select(func.count(GeneratedImage.id)).where(condition)) or 0
    rows = db.execute(
        select(GeneratedImage, User.email, User.full_name)
        .join(User, User.id == GeneratedImage.user_id, isouter=True)
        .where(condition)
        .order_by(GeneratedImage.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return ImageHistoryPage(
        total=total,
        scope=scope,
        items=[
            GeneratedImageOut(
                id=img.id,
                user_id=img.user_id,
                user_email=email,
                user_name=name,
                department=img.department,
                prompt=img.prompt,
                provider=img.provider,
                mime_type=img.mime_type,
                created_at=img.created_at.isoformat() + "Z",
            )
            for img, email, name in rows
        ],
    )


def _can_view(user: User, img: GeneratedImage) -> bool:
    if user.role == ROLE_ADMIN or img.user_id == user.id:
        return True
    return user.role == ROLE_HEAD and img.department is not None and img.department == user.department


@router.get("/{image_id}")
def get_image(
    image_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: CurrentUser,
) -> Response:
    """Serve a stored diagram (decrypted). Owner, Admin, or the department's head."""
    img = db.get(GeneratedImage, image_id)
    # 404 (not 403) so one department's image ids aren't probeable by another
    if img is None or not _can_view(user, img):
        raise HTTPException(404, "Image not found")
    path = Path(img.file_path or "")
    if not path.is_file():
        raise HTTPException(404, "Stored image is missing")
    try:
        data = read_decrypted(path)
    except DecryptionError:
        raise HTTPException(500, "Image cannot be decrypted with the configured key")
    log_action(
        db,
        user,
        "image.download",
        "image",
        img.id,
        ip_address=request.client.host if request.client else None,
    )
    stamp = img.created_at.strftime("%Y%m%d-%H%M")
    ext = mimetypes.guess_extension(img.mime_type or "") or ".png"
    return Response(
        data,
        media_type=img.mime_type or "image/png",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(f'diagram-{stamp}{ext}')}"},
    )
