"""Instance metadata and live tier status for the UI."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.auth.dependencies import CurrentUser
from app.auth.rbac import ACCESS_LEVELS, ALL_ROLES
from app.config import get_settings
from app.llm import router as llm

router = APIRouter(prefix="/api/system", tags=["system"])


class Meta(BaseModel):
    app_name: str
    version: str
    auth_provider: str
    password_min_length: int


@router.get("/meta", response_model=Meta)
def meta() -> Meta:
    """Public: what the sign-in page needs to know."""
    s = get_settings()
    return Meta(
        app_name=s.app_name,
        version=s.app_version,
        auth_provider=s.auth_provider,
        password_min_length=s.password_min_length,
    )


class TierStatus(BaseModel):
    tier: str
    tier_label: str
    provider: str
    model: str
    enabled: bool
    position: int | None
    healthy: bool
    circuit_open: bool
    requires_confirmation: bool | None = None
    monthly_budget_usd: float | None = None
    month_spend_usd: float | None = None


class Status(BaseModel):
    tiers: list[TierStatus]
    roles: list[str]
    departments: list[str]
    access_levels: list[str]
    allowed_extensions: list[str]
    max_file_size_mb: int
    image_generation: bool


@router.get("/status", response_model=Status)
def status(user: CurrentUser) -> Status:
    s = get_settings()
    return Status(
        tiers=[TierStatus(**t) for t in llm.status()],
        roles=ALL_ROLES,
        departments=s.department_list,
        access_levels=list(ACCESS_LEVELS),
        allowed_extensions=sorted(s.allowed_extensions),
        max_file_size_mb=s.max_file_size_mb,
        image_generation=s.image_generation_enabled and bool(s.gemini_api_key),
    )
