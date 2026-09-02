"""Webhook de WhatsApp fijado a NIVEL APP (no por WABA).

El override_callback_uri por WABA (routers/whatsapp_connect_api.py,
routers/whatsapp_connection.py) requiere que Meta haya aprobado el estatus de
Tech Provider / Solution Partner de la app — esa solicitud sigue pendiente, así
que Meta acepta la suscripción (200) pero nunca activa el override. Suscribir
la app entera al objeto whatsapp_business_account SÍ funciona sin ese estatus
y hace que Meta mande los mensajes de todos los números al webhook aquí
configurado. Hoy eso solo se podía hacer a mano en el Meta App Dashboard; este
router lo expone desde la API.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.config import settings
from routers.whatsapp_access import _require_user

router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])

GRAPH_API = "https://graph.facebook.com/v21.0"
META_APP_ID = settings.wa2_meta_app_id
META_APP_SECRET = settings.wa2_meta_app_secret
WA2_VERIFY_TOKEN = settings.wa2_verify_token
WA2_WEBHOOK_URL = settings.wa2_webhook_url

_APP_TOKEN = f"{META_APP_ID}|{META_APP_SECRET}"


def _suscripcion_whatsapp(data: list[dict]) -> dict | None:
    for sub in data:
        if sub.get("object") == "whatsapp_business_account":
            return sub
    return None


@router.get("/app-webhook")
async def wa2_app_webhook_status(request: Request):
    await _require_user(request)
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.get(f"{GRAPH_API}/{META_APP_ID}/subscriptions", params={"access_token": _APP_TOKEN})
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Meta respondió con error: {r.text[:200]}")
    sub = _suscripcion_whatsapp(r.json().get("data", []))
    if not sub:
        return {"callback_url": None}
    return {"callback_url": sub.get("callback_url"), "fields": sub.get("fields", []), "active": sub.get("active")}


@router.post("/app-webhook")
async def wa2_app_webhook_fix(request: Request):
    await _require_user(request)
    if not WA2_VERIFY_TOKEN or not META_APP_SECRET:
        raise HTTPException(status_code=503,
            detail="Falta configurar WA2_VERIFY_TOKEN o el secreto de la app de Meta en el servidor; "
                   "no se puede fijar el webhook de la app.")

    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(f"{GRAPH_API}/{META_APP_ID}/subscriptions",
                         params={"access_token": _APP_TOKEN},
                         json={"object": "whatsapp_business_account", "callback_url": WA2_WEBHOOK_URL,
                               "verify_token": WA2_VERIFY_TOKEN,
                               "fields": "messages,message_template_status_update,account_update"})
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Meta respondió con error al suscribir el webhook: {r.text[:200]}")
        r2 = await c.get(f"{GRAPH_API}/{META_APP_ID}/subscriptions", params={"access_token": _APP_TOKEN})

    callback_url = None
    if r2.status_code < 300:
        sub = _suscripcion_whatsapp(r2.json().get("data", []))
        callback_url = sub.get("callback_url") if sub else None
    return {"ok": callback_url == WA2_WEBHOOK_URL, "callback_url": callback_url}
