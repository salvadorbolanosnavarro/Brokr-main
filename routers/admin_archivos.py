"""Consola de administrador · reporte de archivos riesgosos (solo lectura).

GET /admin/archivos/reporte → CSV con cuenta, bucket, ruta y motivo. Solo
nombres y metadatos de Storage: no abre, copia ni borra archivos. Lógica en
core/reporte_archivos.py.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from core.admin import require_admin
from core.reporte_archivos import a_csv, construir


router = APIRouter()
log = logging.getLogger("broquer.archivos")


@router.get("/admin/archivos/reporte")
async def reporte_archivos(request: Request, sensibles: bool = True):
    await require_admin(request)
    try:
        filas, _ = await construir(incluir_sensibles=sensibles, avisar=log.warning)
    except Exception as exc:
        log.warning("reporte de archivos falló: %s", type(exc).__name__)
        raise HTTPException(503, "No se pudo generar el reporte de archivos. Intenta más tarde.") from None
    fecha = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return Response(
        content=a_csv(filas),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="reporte-archivos-{fecha}.csv"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
