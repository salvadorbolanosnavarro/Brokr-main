"""Read-only EasyBroker API diagnostics."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.auth import get_user_id_from_token
from core.easybroker import EB_BASE, eb_headers
from routers.easybroker_config import get_eb_key_for_user


router = APIRouter()


@router.get("/easybroker/diagnostico")
async def easybroker_diagnostico(request: Request):
    """
    Herramienta de diagnóstico. Le hace a EasyBroker las mismas preguntas que
    hace la importación y reporta EXACTAMENTE qué contesta, para saber si
    respeta el filtro de estatus y con qué nombre manda cada dato.
    No guarda nada.
    """
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Tu sesión expiró. Vuelve a iniciar sesión.")
    user_key = await get_eb_key_for_user(user_id)
    if not user_key:
        raise HTTPException(status_code=400, detail="No tienes API key de EasyBroker configurada.")

    out = {"version_api": "4.8"}

    def _total(d):
        pag = d.get("pagination") or {}
        return pag.get("total") or pag.get("total_entries") or pag.get("count")

    async with httpx.AsyncClient(timeout=30) as client:
        # 1) Sin ningún filtro
        try:
            r0 = await client.get(
                f"{EB_BASE}/properties",
                headers=eb_headers(user_key),
                params={"limit": 50, "page": 1},
            )
            d0 = r0.json() if r0.status_code == 200 else {}
            out["sin_filtro_http"] = r0.status_code
            out["sin_filtro_total"] = _total(d0)
            contenido = d0.get("content") or []
            out["sin_filtro_en_pagina"] = len(contenido)
            if contenido:
                primera = contenido[0]
                out["campos_del_listado"] = sorted(primera.keys())
                out["status_en_listado"] = primera.get("status")
                out["primer_public_id"] = primera.get("public_id")
                # Qué valores de estatus aparecen en esta página
                vistos = {}
                for p in contenido:
                    v = str(p.get("status"))
                    vistos[v] = vistos.get(v, 0) + 1
                out["status_vistos_en_pagina"] = vistos
        except Exception as e:
            out["sin_filtro_error"] = str(e)[:200]

        # 2) Con filtro, probando las dos formas de escribirlo
        for etiqueta, params in (
            ("corchetes", [("limit", 50), ("page", 1), ("search[statuses][]", "published")]),
            ("sin_corchetes", [("limit", 50), ("page", 1), ("search[statuses]", "published")]),
        ):
            try:
                r1 = await client.get(
                    f"{EB_BASE}/properties",
                    headers=eb_headers(user_key),
                    params=params,
                )
                d1 = r1.json() if r1.status_code == 200 else {}
                out[f"filtro_{etiqueta}_http"] = r1.status_code
                out[f"filtro_{etiqueta}_total"] = _total(d1)
            except Exception as e:
                out[f"filtro_{etiqueta}_error"] = str(e)[:200]

        # 3) Filtro por vendidas, para comparar contra el total
        try:
            r2 = await client.get(
                f"{EB_BASE}/properties",
                headers=eb_headers(user_key),
                params=[("limit", 50), ("page", 1), ("search[statuses][]", "sold")],
            )
            d2 = r2.json() if r2.status_code == 200 else {}
            out["filtro_vendidas_http"] = r2.status_code
            out["filtro_vendidas_total"] = _total(d2)
        except Exception as e:
            out["filtro_vendidas_error"] = str(e)[:200]

        # 4) Detalle de una propiedad: qué campos trae y cómo llama al estatus
        pid = out.get("primer_public_id")
        if pid:
            try:
                rd = await client.get(
                    f"{EB_BASE}/properties/{pid}",
                    headers=eb_headers(user_key),
                )
                out["detalle_http"] = rd.status_code
                if rd.status_code == 200:
                    det = rd.json()
                    out["campos_del_detalle"] = sorted(det.keys())
                    out["status_en_detalle"] = det.get("status")
            except Exception as e:
                out["detalle_error"] = str(e)[:200]

    return out
