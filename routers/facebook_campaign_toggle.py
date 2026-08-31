"""Activate or pause a Facebook campaign and its descendants."""
from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from core.auth import get_user_id_from_token
from core.facebook_connection_store import get_facebook_meta
from core.facebook_graph import _fb_batch, _fb_friendly_error, _fb_paginate, _fb_request

router = APIRouter()


@router.post("/facebook/campaign/toggle")
async def facebook_campaign_toggle(request: Request):
    """Activa o pausa una campaña y todos sus adsets y ads hijos."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")

    body = await request.json()
    campaign_id = str(body.get("campaign_id", "") or "").strip()
    new_status = body.get("status", "PAUSED")
    if not campaign_id:
        raise HTTPException(status_code=400, detail="campaign_id requerido")
    if new_status not in ("ACTIVE", "PAUSED"):
        raise HTTPException(status_code=400, detail="status debe ser ACTIVE o PAUSED")

    meta = await get_facebook_meta(user_id)
    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")

    failures: list[dict] = []

    def record_failure(level: str, resource_id: str, response) -> None:
        failures.append(
            {
                "nivel": level,
                "id": resource_id,
                "detalle": _fb_friendly_error(
                    response.text if response is not None else "",
                    f"No se pudo cambiar el {level}",
                ),
            }
        )

    async with httpx.AsyncClient(timeout=30) as client:
        adsets = await _fb_paginate(
            client,
            f"{campaign_id}/adsets",
            token=user_token,
            params={"fields": "id", "limit": "50"},
            prefix="Error leyendo los conjuntos de anuncios",
        )
        adset_ids = [adset["id"] for adset in adsets if adset.get("id")]

        ad_ids: list[str] = []
        for adset_id in adset_ids:
            try:
                ads = await _fb_paginate(
                    client,
                    f"{adset_id}/ads",
                    token=user_token,
                    params={"fields": "id", "limit": "50"},
                    prefix="Error leyendo los anuncios",
                )
                ad_ids.extend([ad["id"] for ad in ads if ad.get("id")])
            except HTTPException as exc:
                failures.append(
                    {"nivel": "anuncios", "id": adset_id, "detalle": str(exc.detail)}
                )

        if new_status == "ACTIVE":
            order = [
                ("anuncio", ad_ids),
                ("conjunto", adset_ids),
                ("campaña", [campaign_id]),
            ]
        else:
            order = [
                ("campaña", [campaign_id]),
                ("conjunto", adset_ids),
                ("anuncio", ad_ids),
            ]

        for level, ids in order:
            if not ids:
                continue
            if len(ids) == 1:
                response = await _fb_request(
                    client,
                    "POST",
                    str(ids[0]),
                    token=user_token,
                    json_body={"status": new_status},
                )
                if response is None or response.status_code not in (200, 201):
                    record_failure(level, ids[0], response)
                continue

            results = await _fb_batch(
                client,
                user_token,
                [
                    {
                        "method": "POST",
                        "relative_url": str(resource_id),
                        "body": f"status={new_status}",
                    }
                    for resource_id in ids
                ],
            )
            for resource_id, result in zip(ids, results):
                if result.get("code") not in (200, 201):
                    response_body = result.get("body")
                    failures.append(
                        {
                            "nivel": level,
                            "id": resource_id,
                            "detalle": _fb_friendly_error(
                                json.dumps(response_body)
                                if isinstance(response_body, dict)
                                else str(response_body),
                                f"No se pudo cambiar el {level}",
                            ),
                        }
                    )

        verified = {}
        try:
            response = await _fb_request(
                client,
                "GET",
                campaign_id,
                token=user_token,
                params={"fields": "status,effective_status"},
            )
            if response is not None and response.status_code == 200:
                verified = response.json() or {}
        except Exception:
            pass

    actual_status = verified.get("status") or ""
    ok = not failures and (actual_status == new_status if actual_status else False)

    response_data = {
        "ok": ok,
        "campaign_id": campaign_id,
        "status": actual_status or new_status,
        "status_solicitado": new_status,
        "effective_status": verified.get("effective_status", ""),
        "adsets": len(adset_ids),
        "ads": len(ad_ids),
        "fallos": failures,
    }
    if not ok:
        summary = "; ".join(failure["detalle"] for failure in failures[:3]) or (
            f"Facebook reporta la campaña en {actual_status or 'estado desconocido'}, "
            f"no en {new_status}."
        )
        response_data["detail"] = (
            f"El cambio quedó incompleto: {summary}. "
            f"Revisa la campaña en Ads Manager antes de confiar en el estado."
        )
        return JSONResponse(status_code=207, content=response_data)
    return response_data
