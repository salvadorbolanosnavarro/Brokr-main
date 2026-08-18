"""Public demo scheduling endpoint.

Extracted from the legacy main module without changing validation, persistence,
rate-limit, or fail-soft notification behavior.
"""
from __future__ import annotations

from datetime import date
import re

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import get_user_id_from_token
from core.config import settings
from core.database import post_rows
from core.legacy_main_config import legacy_main_settings
from limites import exigir_cupo


router = APIRouter()

DEMO_NOTIF_EMAIL = legacy_main_settings.demo_notif_email
_RESEND_KEY_DEMO = settings.resend_api_key
_RESEND_FROM_DEMO = settings.resend_from


class DemoRequest(BaseModel):
    nombre: str
    contacto: str
    fecha: str
    hora: str
    mensaje: str = ""
    origen: str = ""


@router.post("/demo/agendar")
async def demo_agendar(req: DemoRequest, request: Request):
    """Guarda una solicitud pública de demo y envía un aviso best-effort."""
    user_id = await get_user_id_from_token(request)
    exigir_cupo(request, user_id)

    nombre = (req.nombre or "").strip()[:120]
    contacto = (req.contacto or "").strip()[:160]
    fecha = (req.fecha or "").strip()[:10]
    hora = (req.hora or "").strip()[:5]
    mensaje = (req.mensaje or "").strip()[:800]
    origen = (req.origen or "").strip()[:20]

    if not nombre or not contacto:
        raise HTTPException(status_code=400, detail="Escribe tu nombre y un teléfono o correo.")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha):
        raise HTTPException(status_code=400, detail="Elige una fecha válida.")
    if not re.fullmatch(r"\d{2}:\d{2}", hora):
        raise HTTPException(status_code=400, detail="Elige una hora válida.")
    try:
        if date.fromisoformat(fecha) < date.today():
            raise HTTPException(status_code=400, detail="La fecha ya pasó. Elige otra.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Elige una fecha válida.")

    fila = {
        "nombre": nombre,
        "contacto": contacto,
        "fecha": fecha,
        "hora": hora,
        "mensaje": mensaje,
        "origen": origen,
        "user_id": user_id,
    }
    try:
        await post_rows(
            "demos_agendadas",
            fila,
            prefer="return=minimal",
            timeout=10,
            accepted_statuses=(200, 201),
        )
    except httpx.HTTPStatusError:
        raise HTTPException(
            status_code=502,
            detail="No se pudo agendar. Intenta de nuevo en un momento.",
        )

    if _RESEND_KEY_DEMO:
        cuerpo = (
            f"<h2>Nueva demo agendada</h2>"
            f"<p><strong>Nombre:</strong> {nombre}</p>"
            f"<p><strong>Contacto:</strong> {contacto}</p>"
            f"<p><strong>Fecha:</strong> {fecha} a las {hora}</p>"
            f"<p><strong>Mensaje:</strong> {mensaje or '—'}</p>"
            f"<p><strong>Origen:</strong> {origen or 'web'}</p>"
        )
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {_RESEND_KEY_DEMO}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": _RESEND_FROM_DEMO,
                        "to": [DEMO_NOTIF_EMAIL],
                        "subject": f"Demo agendada: {nombre} — {fecha} {hora}",
                        "html": cuerpo,
                    },
                )
        except Exception:
            pass

    return {"ok": True}
