"""Legacy non-destructive admin account mutations extracted from main.py."""
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.database import patch_rows_no_response
from core.legacy_admin import require_legacy_admin
from core.module_access import TOGGLEABLE_MODULES, normalize_disabled_modules


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


class AdminModulosReq(BaseModel):
    user_id: str
    modulos_desactivados: List[str] = []


@router.post("/admin/user/modulos")
async def admin_set_modulos(req: AdminModulosReq, request: Request):
    """Elige qué módulos puede usar una cuenta, sin tocar su rol ni su plan."""
    await require_legacy_admin(request)

    target_id = (req.user_id or "").strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="user_id requerido.")

    modulos = normalize_disabled_modules(req.modulos_desactivados)
    desconocidos = [m for m in modulos if m not in TOGGLEABLE_MODULES]
    if desconocidos:
        raise HTTPException(
            status_code=400,
            detail=f"Módulo(s) inválido(s): {', '.join(desconocidos)}",
        )

    try:
        await patch_rows_no_response(
            "usuarios",
            {"id": f"eq.{target_id}"},
            {"modulos_desactivados": modulos},
            prefer="return=minimal",
            timeout=10,
            accepted_statuses=(200, 204),
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=500, detail=f"Error actualizando módulos: {exc.response.text}")

    return {"ok": True, "user_id": target_id, "modulos_desactivados": modulos}


class AdminAccesoCompletoReq(BaseModel):
    user_id: str
    hasta: Optional[str] = None  # ISO 8601; None revoca el acceso completo


@router.post("/admin/user/acceso-completo")
async def admin_set_acceso_completo(req: AdminAccesoCompletoReq, request: Request):
    """Da (o quita) acceso completo a una cuenta, con fecha de término.

    Es independiente del rol "equipo": permite premiar a un usuario regular
    con todas las funciones de Broquer Max hasta una fecha específica, sin
    convertirlo en parte del equipo interno.
    """
    await require_legacy_admin(request)

    target_id = (req.user_id or "").strip()
    if not target_id:
        raise HTTPException(status_code=400, detail="user_id requerido.")

    hasta_iso = None
    if req.hasta:
        try:
            hasta_dt = datetime.fromisoformat(str(req.hasta).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Fecha de término inválida.")
        if hasta_dt.tzinfo is None:
            hasta_dt = hasta_dt.replace(tzinfo=timezone.utc)
        if hasta_dt <= datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="La fecha de término debe ser futura.")
        hasta_iso = hasta_dt.isoformat()

    try:
        await patch_rows_no_response(
            "usuarios",
            {"id": f"eq.{target_id}"},
            {"acceso_completo_hasta": hasta_iso},
            prefer="return=minimal",
            timeout=10,
            accepted_statuses=(200, 204),
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=500, detail=f"Error actualizando acceso completo: {exc.response.text}")

    return {"ok": True, "user_id": target_id, "acceso_completo_hasta": hasta_iso}
