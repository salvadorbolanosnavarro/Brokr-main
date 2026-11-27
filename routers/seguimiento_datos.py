"""Acceso del piloto y lectura/escritura de las tablas seg_*.

El piloto se limita a las cuentas autorizadas para Cecil
(CECIL_UI_USER_IDS): no se habilita para nadie más sin una nueva
aprobación. Las tablas seg_* se crean con migracion-seguimiento-piloto.sql;
si todavía no existen, la API responde con un mensaje claro en vez de un 500.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException, Request

from core.auth import require_user_id
from core.config import settings
from core.database import delete_rows, get_rows, patch_rows, post_rows, upsert_rows


log = logging.getLogger("broquer.seguimiento")
FALTA_MIGRACION = ("El seguimiento automático todavía no está instalado en la base. "
                   "Corre migracion-seguimiento-piloto.sql en Supabase.")


def usuarios_piloto() -> set[str]:
    return {x.strip() for x in (settings.cecil_ui_user_ids or "").split(",") if x.strip()}


def es_piloto(user_id: str | None) -> bool:
    return bool(user_id) and user_id in usuarios_piloto()


async def usuario_piloto(request: Request) -> str:
    user_id = await require_user_id(request, detail="Inicia sesión.")
    if not es_piloto(user_id):
        raise HTTPException(status_code=403, detail="El seguimiento automático está en piloto privado.")
    return user_id


def _falta_tabla(exc: httpx.HTTPStatusError) -> bool:
    texto = exc.response.text or ""
    return exc.response.status_code == 404 or "42P01" in texto or "PGRST205" in texto


async def leer(tabla: str, params: dict) -> list[dict]:
    try:
        return await get_rows(tabla, params, timeout=15)
    except httpx.HTTPStatusError as exc:
        if tabla.startswith("seg_") and _falta_tabla(exc):
            raise HTTPException(status_code=503, detail=FALTA_MIGRACION) from exc
        log.warning("seguimiento: lectura %s falló (%s)", tabla, exc.response.status_code)
        raise HTTPException(status_code=502, detail="No se pudo leer la información. Intenta de nuevo.") from exc


async def crear(tabla: str, fila: dict | list) -> list[dict]:
    try:
        return await post_rows(tabla, fila, timeout=15)
    except httpx.HTTPStatusError as exc:
        if _falta_tabla(exc):
            raise HTTPException(status_code=503, detail=FALTA_MIGRACION) from exc
        if exc.response.status_code == 409:
            return []
        log.warning("seguimiento: alta en %s falló: %s", tabla, exc.response.text[:200])
        raise HTTPException(status_code=502, detail="No se pudo guardar. Intenta de nuevo.") from exc


async def actualizar(tabla: str, params: dict, cambios: dict) -> list[dict]:
    try:
        return await patch_rows(tabla, params, cambios, prefer="return=representation", timeout=15) or []
    except httpx.HTTPStatusError as exc:
        if _falta_tabla(exc):
            raise HTTPException(status_code=503, detail=FALTA_MIGRACION) from exc
        log.warning("seguimiento: cambio en %s falló: %s", tabla, exc.response.text[:200])
        raise HTTPException(status_code=502, detail="No se pudo guardar el cambio.") from exc


async def guardar(tabla: str, fila: dict, conflicto: str) -> list[dict]:
    try:
        return await upsert_rows(tabla, fila, conflict=conflicto, timeout=15)
    except httpx.HTTPStatusError as exc:
        if _falta_tabla(exc):
            raise HTTPException(status_code=503, detail=FALTA_MIGRACION) from exc
        log.warning("seguimiento: guardado en %s falló: %s", tabla, exc.response.text[:200])
        raise HTTPException(status_code=502, detail="No se pudo guardar.") from exc


async def borrar(tabla: str, params: dict) -> None:
    try:
        await delete_rows(tabla, params, timeout=15)
    except httpx.HTTPStatusError as exc:
        if _falta_tabla(exc):
            raise HTTPException(status_code=503, detail=FALTA_MIGRACION) from exc
        raise HTTPException(status_code=502, detail="No se pudo borrar.") from exc


def en_lista(ids) -> str:
    limpios = [str(i) for i in ids if i and all(c.isalnum() or c in "-_" for c in str(i))]
    return f"in.({','.join(limpios)})" if limpios else "in.(00000000-0000-0000-0000-000000000000)"


async def ajustes_de(user_id: str) -> dict:
    filas = await leer("seg_ajustes", {"user_id": f"eq.{user_id}", "select": "*", "limit": "1"})
    base = {"user_id": user_id, "numero_id": None, "eventos_activos": False, "plantilla_precio": None,
            "plantilla_coincidencia": None, "idioma": "es_MX", "tope_diario": 60, "hora_inicio": 9,
            "hora_fin": 20, "resumen_diario": True, "ultimo_resumen": None}
    if filas:
        base.update({k: v for k, v in filas[0].items() if v is not None or k in ("numero_id", "ultimo_resumen")})
    return base
