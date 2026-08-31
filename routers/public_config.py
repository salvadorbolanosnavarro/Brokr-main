"""Public frontend bootstrap configuration."""
from fastapi import APIRouter

from core.config import settings


router = APIRouter()


@router.get("/config/public")
async def get_public_config():
    """Return non-secret frontend configuration."""
    return {"fb_app_id": settings.legacy_main_fb_app_id}
