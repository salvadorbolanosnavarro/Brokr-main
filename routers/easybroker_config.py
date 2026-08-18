"""EasyBroker organization-level connection settings."""
from __future__ import annotations

from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import get_user_id_from_token
from core.config import settings
from core.database import delete_rows, get_rows, post_rows
from routers.organizaciones import exigir_gestion_integraciones, get_org_id_for_user


router = APIRouter()
SUPABASE_URL = settings.supabase_url
SUPABASE_KEY = settings.supabase_anon_key
EB_BASE = "https://api.easybroker.com/v1"


class EbKeyRequest(BaseModel):
    key: str


async def get_eb_key_for_user(user_id: str) -> str | None:
    """Return the EasyBroker key shared by the user's organization, fail-soft."""
    if not user_id or not SUPABASE_URL or not SUPABASE_KEY:
        return None
    org_id = await get_org_id_for_user(user_id)
    if not org_id:
        return None
    try:
        rows = await get_rows(
            "user_integrations",
            {
                "org_id": f"eq.{org_id}",
                "provider": "eq.easybroker",
                "select": "api_key",
                "limit": "1",
            },
            timeout=8,
        )
        return (rows[0].get("api_key") or "").strip() or None if rows else None
    except Exception:
        return None


@router.post("/config/eb-key")
async def set_eb_key(req: EbKeyRequest, request: Request):
    user_id = await exigir_gestion_integraciones(request)
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado en el servidor.")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            test = await client.get(
                f"{EB_BASE}/properties?limit=1",
                headers={"X-Authorization": req.key.strip(), "accept": "application/json"},
            )
            print(
                f"[set_eb_key] EasyBroker validation status: {test.status_code}, "
                f"body[:200]: {test.text[:200]}"
            )
            if test.status_code == 401:
                raise HTTPException(
                    status_code=400,
                    detail="API key de EasyBroker invalida. Verifica que la copiaste correctamente.",
                )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[set_eb_key] Excepcion en validacion: {type(e).__name__}: {e}")
        pass

    payload = {
        "user_id": user_id,
        "org_id": await get_org_id_for_user(user_id),
        "provider": "easybroker",
        "api_key": req.key.strip(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    try:
        await post_rows(
            "user_integrations",
            payload,
            prefer="resolution=merge-duplicates,return=minimal",
            timeout=10,
        )
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        err_body = e.response.text or ""
        print(f"[set_eb_key] Supabase respondió {status}: {err_body}")
        raise HTTPException(
            status_code=500,
            detail=(
                f"No se pudo guardar la API key (Supabase {status}). "
                "Reintenta o avisa a soporte si persiste."
            ),
        )
    return {"ok": True, "saved": True, "scope": "user"}


@router.delete("/config/eb-key")
async def delete_eb_key(request: Request):
    user_id = await exigir_gestion_integraciones(request)
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase no está configurado.")
    try:
        await delete_rows(
            "user_integrations",
            {
                "org_id": f"eq.{await get_org_id_for_user(user_id)}",
                "provider": "eq.easybroker",
            },
            timeout=10,
        )
    except httpx.HTTPStatusError:
        pass
    return {"ok": True, "deleted": True}


@router.get("/config/eb-key")
async def get_eb_key(request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        return {"configured": False, "masked": ""}
    key = await get_eb_key_for_user(user_id)
    if key and len(key) > 4:
        masked = "*" * (len(key) - 4) + key[-4:]
    else:
        masked = ""
    return {"configured": bool(key), "masked": masked}
