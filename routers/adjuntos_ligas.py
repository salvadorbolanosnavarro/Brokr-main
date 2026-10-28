"""Ligas temporales para los adjuntos del historial (bucket adjuntos-historial).

El bucket guarda archivos de clientes (identificaciones, comprobantes,
contratos). Para poder hacerlo privado, las pantallas ya no abren la liga
pública guardada en actividades/tareas.adjuntos: le piden aquí una liga
firmada que dura una hora.

Quién puede pedir la liga: solo quien puede VER la actividad o tarea que tiene
ese adjunto. Eso se comprueba consultando actividades/tareas con la sesión del
propio usuario, así que deciden las mismas reglas RLS que ya usa la app
(organización, asignaciones, permisos). Las ligas viejas guardadas en el
historial siguen sirviendo como "nombre" del archivo: no hay que migrarlas.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import require_user_id
from core.config import settings
from core.database import rest_url
from core.storage import create_signed_object_url


router = APIRouter()
log = logging.getLogger("broquer.adjuntos")

BUCKET = "adjuntos-historial"
DURACION_SEGUNDOS = 3600
MAX_URLS = 60
TABLAS_CON_ADJUNTOS = ("actividades", "tareas")
_RUTA_RE = re.compile(r"/storage/v1/object/(?:public|sign|authenticated)/adjuntos-historial/([A-Za-z0-9._-]{1,200})(?:\?|$)")


class LigasReq(BaseModel):
    urls: list[str]


def ruta_de_url(url: str) -> str | None:
    """Nombre del archivo dentro del bucket, o None si la liga no es de adjuntos-historial."""
    # El dominio no importa para la seguridad: la liga solo se firma si una
    # actividad/tarea visible para el usuario la tiene guardada tal cual.
    if not isinstance(url, str) or not url.startswith("https://"):
        return None
    m = _RUTA_RE.search(url)
    if not m or m.group(1).startswith("."):
        return None
    return m.group(1)


def _token(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    return auth[7:].strip() if auth.lower().startswith("bearer ") else ""


async def _usuario_ve_adjunto(client: httpx.AsyncClient, token: str, url: str) -> bool:
    """¿Alguna actividad o tarea VISIBLE para este usuario (RLS) tiene esta liga?"""
    headers = {"apikey": settings.supabase_anon_key, "Authorization": f"Bearer {token}"}
    filtro = "cs." + json.dumps([{"url": url}], separators=(",", ":"))
    for tabla in TABLAS_CON_ADJUNTOS:
        try:
            r = await client.get(rest_url(tabla), headers=headers,
                                 params={"select": "id", "adjuntos": filtro, "limit": "1"})
        except httpx.HTTPError as exc:
            log.warning("adjuntos: no se pudo revisar %s: %s", tabla, exc)
            continue
        if r.status_code == 200:
            filas = r.json()
            if isinstance(filas, list) and filas:
                return True
    return False


async def _liga(client: httpx.AsyncClient, token: str, url: str) -> str | None:
    ruta = ruta_de_url(url)
    if not ruta or not await _usuario_ve_adjunto(client, token, url):
        return None
    try:
        return await create_signed_object_url(BUCKET, ruta, expires_in=DURACION_SEGUNDOS)
    except Exception as exc:
        log.warning("adjuntos: no se pudo firmar %s: %s", ruta, exc)
        return None


@router.post("/adjuntos/ligas")
async def adjuntos_ligas(req: LigasReq, request: Request) -> dict[str, Any]:
    """Regresa {"ligas": {url_guardada: liga_firmada_o_null}, "segundos": 3600}."""
    await require_user_id(request)
    token = _token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Sesión requerida.")
    urls = list(dict.fromkeys(u for u in req.urls if isinstance(u, str)))[:MAX_URLS]
    async with httpx.AsyncClient(timeout=15) as client:
        firmadas = await asyncio.gather(*(_liga(client, token, u) for u in urls))
    return {"ligas": dict(zip(urls, firmadas)), "segundos": DURACION_SEGUNDOS}
