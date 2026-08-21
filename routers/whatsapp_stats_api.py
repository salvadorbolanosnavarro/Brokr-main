"""WhatsApp statistics I/O wrapper around the pure aggregation engine."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request

from core.config import settings
from core.database import get_rows
from routers.whatsapp_access import _ids_visibles, _require_user
from routers.whatsapp_stats import _agrega_ventana
from routers.whatsapp_utils import in_filter as _in_filter


router = APIRouter(prefix="/whatsapp2", tags=["whatsapp2"])
log = logging.getLogger("broquer.whatsapp2")
_ZONA_DEFAULT = settings.wa2_zone_default
_VENTANAS_ESTAD = {"semana": 7, "mes": 30, "trimestre": 90, "todo": 0}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _sb_diag(table: str, params: dict) -> tuple[list, str]:
    """Diagnostic read: unlike fail-soft helpers, preserve database error text."""
    try:
        data = await get_rows(table, params, timeout=25)
        return data, ""
    except httpx.HTTPStatusError as exc:
        r = exc.response
        return [], f"{r.status_code}: {r.text[:200]}"
    except Exception as exc:
        return [], str(exc)[:200]


async def _sb_get_paginado(table: str, params: dict, tope: int = 40000,
                           paralelo: int = 6) -> tuple[list, str]:
    salida: list = []
    error = ""
    pagina = 1000
    bloque = 0
    while len(salida) < tope and bloque < 40:
        tareas = []
        for k in range(paralelo):
            p = dict(params)
            p["limit"] = str(pagina)
            p["offset"] = str((bloque * paralelo + k) * pagina)
            tareas.append(_sb_diag(table, p))
        resultados = await asyncio.gather(*tareas, return_exceptions=True)
        traidas = 0
        for res in resultados:
            if isinstance(res, Exception):
                error = error or str(res)[:200]
                continue
            filas, err = res
            if err:
                error = error or err
                continue
            salida.extend(filas)
            traidas += len(filas)
        if error and not salida:
            break
        if traidas < pagina * paralelo:
            break
        bloque += 1
    return salida[:tope], error


@router.get("/estadisticas")
async def wa2_estadisticas(request: Request, zona: str | None = None):
    user_id = await _require_user(request)
    ids = await _ids_visibles(user_id)
    filtro = _in_filter(ids)
    zona = zona or _ZONA_DEFAULT

    (numeros, e_num), (contactos, e_con), (conversaciones, e_conv), (mensajes, e_msg) = await asyncio.gather(
        _sb_diag("wa2_numeros", {"user_id": filtro, "select": "*"}),
        _sb_get_paginado("wa2_contactos", {"user_id": filtro, "order": "id.asc", "select": "*"}, tope=20000),
        _sb_get_paginado("wa2_conversaciones", {"user_id": filtro, "order": "id.asc", "select": "*"}, tope=20000),
        _sb_get_paginado(
            "wa2_mensajes",
            {"user_id": filtro, "order": "id.asc", "select": "conversacion_id,direction,sender,created_at"},
        ),
    )
    if e_msg and not mensajes:
        mensajes, e_msg2 = await _sb_get_paginado(
            "wa2_mensajes", {"user_id": filtro, "order": "id.asc", "select": "*"}
        )
        if mensajes:
            e_msg = ""
        else:
            e_msg = e_msg2 or e_msg

    for n in numeros:
        n.pop("access_token", None)

    diagnostico = {
        "user_ids": len(ids),
        "numeros": len(numeros),
        "contactos": len(contactos),
        "conversaciones": len(conversaciones),
        "mensajes": len(mensajes),
        "errores": {
            k: v
            for k, v in {
                "wa2_numeros": e_num,
                "wa2_contactos": e_con,
                "wa2_conversaciones": e_conv,
                "wa2_mensajes": e_msg,
            }.items()
            if v
        },
    }
    if diagnostico["errores"]:
        log.error("estadisticas whatsapp2: %s", diagnostico["errores"])

    ahora = datetime.now(timezone.utc)
    ventanas = {
        nombre: _agrega_ventana(dias, ahora, zona, contactos, conversaciones, mensajes, numeros)
        for nombre, dias in _VENTANAS_ESTAD.items()
    }
    return {
        "ok": True,
        "zona": zona,
        "generado": _now(),
        "numeros_conectados": len(numeros),
        "diagnostico": diagnostico,
        "ventanas": ventanas,
    }
