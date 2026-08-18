"""Telemetry heartbeat endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from core.auth import get_user_id_from_token
from core.config import settings
from core.database import post_rows
from core.telemetry import MODULOS_VALIDOS


router = APIRouter()


class TelemetriaSesionModuloReq(BaseModel):
    modulo: str
    segundos: int


@router.post("/telemetria/sesion-modulo")
async def telemetria_sesion_modulo(req: TelemetriaSesionModuloReq, request: Request):
    """Heartbeat del frontend; fail-soft porque no es trabajo crítico."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        return {"ok": False}
    modulo = (req.modulo or "").strip().lower()[:40]
    if modulo not in MODULOS_VALIDOS:
        return {"ok": False, "razon": "modulo_invalido"}
    segs = int(req.segundos or 0)
    if segs <= 0 or segs > 3600:
        return {"ok": False, "razon": "segundos_invalidos"}
    if not settings.supabase_url or not settings.supabase_service_key:
        return {"ok": False}
    try:
        await post_rows(
            "module_sessions",
            {"user_id": user_id, "modulo": modulo, "segundos": segs},
            prefer="return=minimal",
            timeout=5,
        )
    except Exception:
        pass
    return {"ok": True}
