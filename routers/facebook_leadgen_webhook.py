"""Fail-closed Facebook Lead Ads POST webhook boundary."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Request, Response

from core.facebook_leadgen_config import FB_WEBHOOK_SECRET
from core.facebook_leadgen_processor import process_facebook_lead


router = APIRouter()
_log = logging.getLogger("broquer.facebook")


@router.post("/facebook/leadgen/webhook")
async def facebook_leadgen_webhook(request: Request, background: BackgroundTasks):
    """Recibe el aviso de Meta y encola la captura del lead."""
    raw = await request.body()

    if not FB_WEBHOOK_SECRET:
        _log.error(
            "FB_APP_SECRET/FB_WEBHOOK_SECRET vacíos: el webhook de Lead Ads "
            "queda CERRADO hasta que se configure uno en Railway."
        )
        return Response(status_code=503)

    firma = request.headers.get("X-Hub-Signature-256", "")
    esperada = "sha256=" + hmac.new(
        FB_WEBHOOK_SECRET.encode(), raw, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(firma, esperada):
        _log.warning("Firma inválida en el webhook de Lead Ads")
        return Response(status_code=403)

    try:
        payload = json.loads(raw)
    except Exception:
        return Response(status_code=200)

    pendientes = []
    for entrada in payload.get("entry") or []:
        for cambio in entrada.get("changes") or []:
            if cambio.get("field") != "leadgen":
                continue
            valor = cambio.get("value") or {}
            if valor.get("leadgen_id"):
                pendientes.append(valor)

    for valor in pendientes:
        background.add_task(process_facebook_lead, valor)

    return Response(status_code=200)
