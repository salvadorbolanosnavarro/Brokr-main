"""WhatsApp de ChatGPT — conexión real vía Meta Embedded Signup.

Router independiente del módulo legacy de WhatsApp. Expone la mínima ruta de
producción para que un agente conecte uno o varios números: configuración
pública, cierre de signup, listado de números y envío de prueba.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import require_user_id
from core.config import settings
from core.database import get_rows, upsert_rows

router = APIRouter(prefix="/whatsapp-chatgpt", tags=["whatsapp-chatgpt"])

META_APP_ID = settings.meta_app_id
META_APP_SECRET = settings.meta_app_secret
META_LOGIN_CONFIG_ID = settings.meta_login_config_id
GRAPH_API_VERSION = settings.meta_graph_version
GRAPH_API = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
WA_REGISTER_PIN = settings.wa_register_pin
FRONTEND_URL = settings.frontend_url


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _user_id(request: Request) -> str:
    return await require_user_id(
        request,
        detail="Inicia sesión para conectar WhatsApp.",
    )


async def _sb_get(table: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        return await get_rows(table, params, timeout=15)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error leyendo {table}.",
        ) from exc


async def _sb_upsert(
    table: str,
    payload: dict[str, Any],
    conflict: str,
) -> list[dict[str, Any]]:
    try:
        return await upsert_rows(
            table,
            payload,
            conflict=conflict,
            timeout=15,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error guardando {table}.",
        ) from exc


def _public_number(row: dict[str, Any]) -> dict[str, Any]:
    """Return a browser-safe WhatsApp number record without Meta credentials."""
    safe = dict(row)
    safe.pop("access_token", None)
    return safe


class CompleteSignupReq(BaseModel):
    code: str
    waba_id: str | None = None
    phone_number_id: str | None = None
    business_id: str | None = None
    register_number: bool = True


class SendMessageReq(BaseModel):
    phone_number_id: str
    to: str
    body: str


@router.get("/config")
async def config(request: Request):
    await _user_id(request)
    missing = [
        key
        for key, value in {
            "META_APP_ID": META_APP_ID,
            "META_APP_SECRET": META_APP_SECRET,
            "META_LOGIN_CONFIG_ID": META_LOGIN_CONFIG_ID,
            "SUPABASE_URL": settings.supabase_url,
            "SUPABASE_SERVICE_KEY": settings.supabase_service_key,
        }.items()
        if not value
    ]
    return {
        "ok": not missing,
        "app_id": META_APP_ID,
        "login_config_id": META_LOGIN_CONFIG_ID,
        "graph_version": GRAPH_API_VERSION,
        "redirect_uri": f"{FRONTEND_URL}/whatsapp-chatgpt.html",
        "missing": missing,
    }


@router.get("/numbers")
async def numbers(request: Request):
    uid = await _user_id(request)
    rows = await _sb_get(
        "wac_numbers",
        {
            "user_id": f"eq.{uid}",
            "select": (
                "id,user_id,waba_id,waba_name,phone_number_id,display_number,"
                "quality_rating,status,created_at,updated_at"
            ),
            "order": "created_at.desc",
        },
    )
    return {"ok": True, "numbers": rows}


@router.post("/complete-signup")
async def complete_signup(req: CompleteSignupReq, request: Request):
    uid = await _user_id(request)
    if not META_APP_ID or not META_APP_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Faltan META_APP_ID y/o META_APP_SECRET.",
        )
    if not req.code.strip():
        raise HTTPException(
            status_code=400,
            detail="Meta no devolvió código de autorización.",
        )

    async with httpx.AsyncClient(timeout=25) as client:
        token_response = await client.get(
            f"{GRAPH_API}/oauth/access_token",
            params={
                "client_id": META_APP_ID,
                "client_secret": META_APP_SECRET,
                "code": req.code,
            },
        )
    if token_response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Meta rechazó el código: {token_response.text[:300]}",
        )

    token_json = token_response.json()
    access_token = token_json.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=400,
            detail="Meta no devolvió access_token.",
        )

    waba_id = (req.waba_id or "").strip()
    phone_number_id = (req.phone_number_id or "").strip()
    business_id = (req.business_id or "").strip()

    if not waba_id:
        async with httpx.AsyncClient(timeout=15) as client:
            debug_response = await client.get(
                f"{GRAPH_API}/debug_token",
                params={
                    "input_token": access_token,
                    "access_token": f"{META_APP_ID}|{META_APP_SECRET}",
                },
            )
        if debug_response.status_code == 200:
            for scope in debug_response.json().get("data", {}).get("granular_scopes", []):
                if (
                    scope.get("scope") == "whatsapp_business_management"
                    and scope.get("target_ids")
                ):
                    waba_id = scope["target_ids"][0]
                    break

    if not waba_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "No pude identificar el WABA. Reintenta el signup y acepta "
                "permisos de WhatsApp."
            ),
        )

    waba_name = "WhatsApp Business"
    display_number = ""
    quality_rating = "UNKNOWN"
    status = "CONNECTED"

    async with httpx.AsyncClient(timeout=20) as client:
        waba_response = await client.get(
            f"{GRAPH_API}/{waba_id}",
            params={
                "access_token": access_token,
                "fields": "id,name,business",
            },
        )
        if waba_response.status_code == 200:
            waba_data = waba_response.json()
            waba_name = waba_data.get("name") or waba_name
            business_id = business_id or (waba_data.get("business") or {}).get("id", "")

        phones_response = await client.get(
            f"{GRAPH_API}/{waba_id}/phone_numbers",
            params={
                "access_token": access_token,
                "fields": "id,display_phone_number,quality_rating,verified_name,status",
            },
        )

    phones = (
        phones_response.json().get("data", [])
        if phones_response.status_code == 200
        else []
    )
    if phone_number_id:
        selected = next(
            (phone for phone in phones if phone.get("id") == phone_number_id),
            None,
        ) or {}
    else:
        selected = phones[0] if phones else {}
        phone_number_id = selected.get("id", "")

    if not phone_number_id:
        raise HTTPException(
            status_code=400,
            detail="No encontré números de WhatsApp en esa cuenta Business.",
        )

    display_number = selected.get("display_phone_number") or display_number
    quality_rating = selected.get("quality_rating") or quality_rating
    status = selected.get("status") or status

    async with httpx.AsyncClient(timeout=20) as client:
        subscribed_response = await client.post(
            f"{GRAPH_API}/{waba_id}/subscribed_apps",
            params={"access_token": access_token},
        )
        registered = False
        register_warning = ""
        if req.register_number:
            register_response = await client.post(
                f"{GRAPH_API}/{phone_number_id}/register",
                params={"access_token": access_token},
                json={
                    "messaging_product": "whatsapp",
                    "pin": WA_REGISTER_PIN,
                },
            )
            registered = register_response.status_code < 400
            if not registered:
                register_warning = register_response.text[:300]

    expires_at = None
    if token_json.get("expires_in"):
        expires_at = (
            datetime.now(timezone.utc)
            + timedelta(seconds=int(token_json["expires_in"]))
        ).isoformat()

    payload = {
        "user_id": uid,
        "business_id": business_id or None,
        "waba_id": waba_id,
        "waba_name": waba_name,
        "phone_number_id": phone_number_id,
        "display_number": display_number,
        "access_token": access_token,
        "token_expires_at": expires_at,
        "quality_rating": quality_rating,
        "status": status,
        "ai_enabled": True,
        "identity_prompt": "",
        "updated_at": _now(),
    }
    rows = await _sb_upsert("wac_numbers", payload, "phone_number_id")
    stored = rows[0] if rows else payload

    return {
        "ok": True,
        "number": _public_number(stored),
        "subscribed": subscribed_response.status_code < 400,
        "registered": registered,
        "register_warning": register_warning,
    }


@router.post("/send-test")
async def send_test(req: SendMessageReq, request: Request):
    uid = await _user_id(request)
    rows = await _sb_get(
        "wac_numbers",
        {
            "user_id": f"eq.{uid}",
            "phone_number_id": f"eq.{req.phone_number_id}",
            "select": "phone_number_id,access_token",
            "limit": "1",
        },
    )
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="Ese número no está conectado a tu cuenta.",
        )

    to = "".join(character for character in req.to if character.isdigit())
    if len(to) < 10:
        raise HTTPException(
            status_code=400,
            detail=(
                "Escribe el teléfono destino con lada, por ejemplo "
                "5215512345678."
            ),
        )

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{GRAPH_API}/{req.phone_number_id}/messages",
            params={"access_token": rows[0]["access_token"]},
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": req.body[:4000],
                },
            },
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=400,
            detail=f"WhatsApp no envió el mensaje: {response.text[:300]}",
        )
    return {"ok": True, "meta": response.json()}
