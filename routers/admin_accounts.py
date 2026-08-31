"""Legacy non-destructive admin account mutations extracted from main.py."""
import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.database import patch_rows_no_response
from core.legacy_admin import require_legacy_admin


router = APIRouter()


class AdminRolReq(BaseModel):
    user_id: str
    rol: str


@router.post("/admin/user/rol")
async def admin_set_rol(req: AdminRolReq, request: Request):
    caller_id = await require_legacy_admin(request)

    ROLES_VALIDOS = {"admin", "equipo", "agente"}
    if req.rol not in ROLES_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Rol inválido. Válidos: {', '.join(sorted(ROLES_VALIDOS))}")

    target_id = (req.user_id or "").strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="user_id requerido.")
    if target_id == caller_id and req.rol != "admin":
        raise HTTPException(status_code=400, detail="No puedes cambiar tu propio rol de admin. Pide a otro admin que lo haga.")

    try:
        await patch_rows_no_response(
            "usuarios",
            {"id": f"eq.{target_id}"},
            {"rol": req.rol},
            prefer="return=minimal",
            timeout=10,
            accepted_statuses=(200, 204),
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=500, detail=f"Error actualizando rol: {exc.response.text}")

    return {"ok": True, "user_id": target_id, "rol": req.rol}


class AdminActivoReq(BaseModel):
    user_id: str
    activo: bool


@router.post("/admin/user/activo")
async def admin_set_activo(req: AdminActivoReq, request: Request):
    caller_id = await require_legacy_admin(request)

    target_id = (req.user_id or "").strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="user_id requerido.")
    if target_id == caller_id and not req.activo:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta de admin.")

    try:
        await patch_rows_no_response(
            "usuarios",
            {"id": f"eq.{target_id}"},
            {"activo": bool(req.activo)},
            prefer="return=minimal",
            timeout=10,
            accepted_statuses=(200, 204),
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=500, detail=f"Error actualizando activo: {exc.response.text}")

    return {"ok": True, "user_id": target_id, "activo": bool(req.activo)}
