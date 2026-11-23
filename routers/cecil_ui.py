"""Per-account visual rollout. Does not grant business permissions or change data."""
from fastapi import APIRouter, Request, Response
from core.auth import require_user_id
from core.config import settings

router = APIRouter()


@router.get('/ui/cecil')
async def cecil_ui(request: Request, response: Response):
    user_id = await require_user_id(request)
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Vary'] = 'Authorization'
    enabled = settings.cecil_ui_enabled
    allowed = {item.strip() for item in settings.cecil_ui_user_ids.split(',') if item.strip()}
    return {'enabled': enabled and user_id in allowed, 'user_id': user_id}
