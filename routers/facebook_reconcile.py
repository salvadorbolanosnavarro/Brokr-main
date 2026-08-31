"""Reconcile Broquer Facebook Ads bookkeeping against Meta state."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.config import settings
from core.database import get_rows
from core.facebook_connection_store import get_facebook_meta
from core.facebook_graph import _fb_friendly_error, _fb_request
from core.facebook_persistence import (
    FACEBOOK_AD_ENTITIES_TABLE,
    facebook_table_missing,
    update_facebook_entity,
    warn_facebook_migration,
)
from routers.organizaciones import exigir_gestion_integraciones

router = APIRouter()


@router.post("/facebook/reconcile")
async def facebook_reconcile(request: Request):
    """Reconcile Broquer's Ads ledger with Meta, preserving legacy cleanup rules."""
    user_id = await exigir_gestion_integraciones(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    limpiar = bool(body.get("limpiar"))

    meta_fb = await get_facebook_meta(user_id)
    user_token = meta_fb.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")

    if not settings.supabase_url or not settings.supabase_service_key:
        raise HTTPException(status_code=500, detail="Supabase no configurado")

    try:
        filas = await get_rows(
            FACEBOOK_AD_ENTITIES_TABLE,
            {"user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": "200"},
            timeout=15,
        )
    except httpx.HTTPStatusError as exc:
        if facebook_table_missing(exc.response):
            warn_facebook_migration("reconciliar", exc.response)
            raise HTTPException(
                status_code=503,
                detail="Falta correr migracion-facebook-ads.sql en Supabase. Sin esa tabla "
                "Broquer no lleva registro de lo que creó y no puede reconciliar.",
            )
        raise HTTPException(status_code=502, detail="No se pudo leer el registro de campañas.")

    sanas, huerfanas, revisar, corregidas = [], [], [], []

    async with httpx.AsyncClient(timeout=40) as client:
        for fila in filas:
            cid = fila.get("campaign_id")
            row_id = fila.get("id")

            if not cid:
                if fila.get("status") == "CREANDO":
                    await update_facebook_entity(
                        row_id,
                        {
                            "status": "FALLIDO",
                            "error_detail": "Creación interrumpida antes de crear la campaña.",
                        },
                    )
                    corregidas.append({"row_id": row_id, "accion": "marcada como fallida"})
                continue

            response = await _fb_request(
                client,
                "GET",
                str(cid),
                token=user_token,
                params={"fields": "id,name,status,effective_status"},
                reintentos=2,
            )
            existe = response is not None and response.status_code == 200
            datos = response.json() if existe else {}

            if not existe:
                await update_facebook_entity(
                    row_id,
                    {
                        "status": "ELIMINADO",
                        "last_checked_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                corregidas.append(
                    {"row_id": row_id, "campaign_id": cid, "accion": "ya no existe en Meta"}
                )
                continue

            eff = datos.get("effective_status", "")
            estado_meta = datos.get("status", "")
            await update_facebook_entity(
                row_id,
                {
                    "status": estado_meta or fila.get("status"),
                    "effective_status": eff,
                    "last_checked_at": datetime.now(timezone.utc).isoformat(),
                },
            )

            incompleta = not fila.get("ad_id")
            if incompleta:
                entrega = eff in ("ACTIVE", "PENDING_REVIEW", "IN_PROCESS")
                if entrega:
                    revisar.append(
                        {
                            "campaign_id": cid,
                            "name": datos.get("name", ""),
                            "effective_status": eff,
                            "motivo": "Incompleta en Broquer pero activa en Meta. "
                            "Revísala a mano antes de borrar.",
                        }
                    )
                elif limpiar:
                    delete_response = await _fb_request(
                        client,
                        "DELETE",
                        str(cid),
                        token=user_token,
                        reintentos=2,
                    )
                    if delete_response is not None and delete_response.status_code in (200, 204):
                        await update_facebook_entity(row_id, {"status": "ELIMINADO"})
                        huerfanas.append(
                            {"campaign_id": cid, "name": datos.get("name", ""), "borrada": True}
                        )
                    else:
                        huerfanas.append(
                            {
                                "campaign_id": cid,
                                "name": datos.get("name", ""),
                                "borrada": False,
                                "detalle": _fb_friendly_error(
                                    delete_response.text if delete_response is not None else "",
                                    "No se pudo borrar",
                                ),
                            }
                        )
                else:
                    huerfanas.append(
                        {
                            "campaign_id": cid,
                            "name": datos.get("name", ""),
                            "borrada": False,
                            "detalle": 'Manda {"limpiar": true} para borrarla.',
                        }
                    )
            else:
                sanas.append(cid)

    return {
        "ok": True,
        "revisadas": len(filas),
        "sanas": len(sanas),
        "huerfanas": huerfanas,
        "requieren_revision_manual": revisar,
        "corregidas": corregidas,
        "limpieza_aplicada": limpiar,
    }
