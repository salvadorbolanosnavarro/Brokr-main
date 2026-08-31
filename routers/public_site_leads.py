"""Public agent-site lead capture endpoint.

Extracted from legacy main.py without changing honeypot, rate-limit, dedupe,
fail-soft PATCH, or create semantics.
"""
from __future__ import annotations

from datetime import datetime, timezone
import random as _rnd
import time as _t

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.config import settings
from core.database import get_rows, patch_rows, post_rows


router = APIRouter()
SUPABASE_URL = settings.supabase_url
SUPABASE_SERVICE_KEY = settings.supabase_service_key

_SITIO_LEAD_RL = {}


def _sitio_lead_permitido(clave: str, limite: int, ventana_seg: int) -> bool:
    ahora = _t.time()
    lst = [t for t in _SITIO_LEAD_RL.get(clave, []) if ahora - t < ventana_seg]
    if len(lst) >= limite:
        _SITIO_LEAD_RL[clave] = lst
        return False
    lst.append(ahora)
    _SITIO_LEAD_RL[clave] = lst
    if len(_SITIO_LEAD_RL) > 5000:
        viejas = [k for k, v in _SITIO_LEAD_RL.items() if not v or ahora - v[-1] > ventana_seg]
        for k in viejas:
            _SITIO_LEAD_RL.pop(k, None)
    return True


class SitioLeadIn(BaseModel):
    nombre: str
    telefono: str = ""
    mensaje: str = ""
    sitio_web: str = ""


@router.post("/sitio/{slug}/lead")
async def sitio_registrar_lead(slug: str, payload: SitioLeadIn, request: Request):
    """Registra un lead proveniente del sitio público del agente."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Servicio no disponible")

    if (payload.sitio_web or "").strip():
        return {"ok": True}

    nombre = (payload.nombre or "").strip()[:120]
    telefono = "".join(ch for ch in (payload.telefono or "") if ch.isdigit() or ch == "+")[:20]
    mensaje = (payload.mensaje or "").strip()[:1000]
    if not nombre:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio")

    ip = (
        request.headers.get("cf-connecting-ip")
        or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        or (request.client.host if request.client else "?")
    )
    if not _sitio_lead_permitido(f"ip:{ip}", 5, 3600) or not _sitio_lead_permitido(
        f"slug:{slug}", 30, 3600
    ):
        raise HTTPException(status_code=429, detail="Demasiadas solicitudes, intenta más tarde")

    async with httpx.AsyncClient(timeout=10) as client:
        hdr = {
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
        }

        try:
            rows = await get_rows(
                "usuarios",
                {
                    "slug": f"eq.{slug}",
                    "sitio_activo": "eq.true",
                    "select": "id",
                    "limit": "1",
                },
                timeout=10,
            )
        except httpx.HTTPStatusError:
            rows = []
        if not rows:
            raise HTTPException(status_code=404, detail="Sitio no encontrado")
        user_id = rows[0]["id"]

        ahora = datetime.now(timezone.utc).isoformat()
        nota = (
            f"Lead del sitio web ({ahora[:10]}): {mensaje}"
            if mensaje
            else f"Lead del sitio web ({ahora[:10]})."
        )

        existente = None
        if telefono:
            try:
                filas = await get_rows(
                    "contactos",
                    {
                        "user_id": f"eq.{user_id}",
                        "telefono": f"eq.{telefono}",
                        "select": "id,notas,es_potencial",
                        "limit": "1",
                    },
                    timeout=10,
                )
            except httpx.HTTPStatusError:
                filas = []
            existente = filas[0] if filas else None

        if existente:
            notas_prev = (existente.get("notas") or "").strip()
            nuevas_notas = (notas_prev + "\n\n" + nota).strip() if notas_prev else nota
            try:
                await patch_rows(
                    "contactos",
                    {"id": f"eq.{existente['id']}"},
                    {
                        "es_potencial": True,
                        "notas": nuevas_notas[:5000],
                        "updated_at": ahora,
                    },
                    timeout=10,
                )
            except httpx.HTTPStatusError:
                pass
            return {"ok": True, "duplicado": True}

        nuevo = {
            "id": f"c_{int(datetime.now(timezone.utc).timestamp() * 1000)}{_rnd.randint(100, 999)}",
            "user_id": user_id,
            "nombre": nombre.upper(),
            "telefono": telefono or None,
            "notas": nota,
            "es_potencial": True,
            "estatus": "nuevo",
            "fuente": "Sitio web",
            "etiquetas": [],
            "operaciones": [],
            "created_at": ahora,
            "updated_at": ahora,
        }
        try:
            await post_rows(
                "contactos",
                nuevo,
                prefer="return=minimal",
                timeout=10,
                accepted_statuses=(200, 201),
            )
        except httpx.HTTPStatusError:
            raise HTTPException(status_code=502, detail="No se pudo registrar el lead")

    return {"ok": True}
