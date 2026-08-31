"""Create Facebook Click-to-Messenger campaigns with idempotent bookkeeping."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import get_user_id_from_token
from core.facebook_connection_store import get_facebook_meta_row
from core.facebook_graph import _fb_exigir_ok, _fb_friendly_error, _fb_paginate, _fb_request
from core.facebook_persistence import reserve_facebook_creation, update_facebook_entity
from routers.organizaciones import get_org_id_for_user

router = APIRouter()
_fb_log = logging.getLogger("broquer.facebook")


class FbCreateAdRequest(BaseModel):
    account_id: str
    campaign_name: str
    ad_text: str = ""
    headline: str = ""
    images_b64: list = []
    images_mime: list = []
    daily_budget_mxn: float = 50.0
    duration_days: int = 7
    age_min: int = 18
    age_max: int = 0
    country: str = "MX"
    city: str = ""
    city_type: str = "city"
    page_id: str = ""
    objective: str = "OUTCOME_ENGAGEMENT"
    publish_now: bool = False
    post_id: str = ""
    idempotency_key: str = ""
    custom_audience_ids: list = []
    excluded_audience_ids: list = []


@router.post("/facebook/create-ad")
async def facebook_create_ad(req: FbCreateAdRequest, request: Request):
    """Create a carousel Click-to-Messenger campaign, preserving the legacy contract."""
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")

    row = await get_facebook_meta_row(user_id)
    if not row:
        raise HTTPException(status_code=400, detail="Facebook no conectado")
    meta = row.get("meta") or {}

    user_token = meta.get("user_token", "")
    if not user_token:
        raise HTTPException(status_code=400, detail="Token sin permisos de ads. Reconecta tu Facebook.")

    page_id = meta.get("page_id", "")
    if not page_id:
        raise HTTPException(
            status_code=400,
            detail="Página de Facebook no identificada. Reconecta tu Facebook desde tu perfil.",
        )

    server_account_id = meta.get("ad_account_id", "")
    if not server_account_id:
        raise HTTPException(
            status_code=400,
            detail="Cuenta publicitaria no seleccionada. Reconecta tu Facebook desde tu perfil.",
        )
    req.account_id = (
        server_account_id if server_account_id.startswith("act_") else f"act_{server_account_id}"
    )
    req.page_id = page_id

    try:
        async with httpx.AsyncClient(timeout=10) as client_v:
            promote_ids = [
                item.get("id")
                for item in await _fb_paginate(
                    client_v,
                    f"{req.account_id}/promote_pages",
                    token=user_token,
                    params={"fields": "id", "limit": "100"},
                    prefix="Error validando la página",
                )
                if item.get("id")
            ]
            if promote_ids and page_id not in promote_ids:
                raise HTTPException(
                    status_code=400,
                    detail="Tu cuenta publicitaria no está autorizada para anunciar tu página de Facebook. Asocia la página a la cuenta en business.facebook.com → Configuración del negocio → Páginas → Asignar a cuenta publicitaria, y luego reconecta Facebook.",
                )
    except HTTPException:
        raise
    except Exception:
        pass

    if req.post_id and "_" not in req.post_id:
        req.post_id = f"{page_id}_{req.post_id}"

    optimization_goal = "CONVERSATIONS"
    billing_event = "IMPRESSIONS"
    target_status = "ACTIVE" if req.publish_now else "PAUSED"
    account_id = req.account_id if req.account_id.startswith("act_") else f"act_{req.account_id}"
    daily_budget_cents = int(req.daily_budget_mxn * 100)

    idem = (req.idempotency_key or "").strip()[:120]
    reserva = await reserve_facebook_creation(
        user_id,
        await get_org_id_for_user(user_id),
        {
            "ad_account_id": account_id,
            "page_id": page_id,
            "campaign_name": (req.campaign_name or "Campaña Broquer")[:120],
            "objective": "OUTCOME_ENGAGEMENT",
            "daily_budget_mxn": req.daily_budget_mxn,
            "duration_days": req.duration_days,
            "meta": {
                "city": req.city,
                "city_type": req.city_type,
                "imagenes": len(req.images_b64 or []),
                "post_id": req.post_id,
                "publish_now": bool(req.publish_now),
            },
        },
        idempotency_key=idem,
    )

    if reserva.get("modo") == "duplicado":
        previa = reserva.get("row") or {}
        estado_previo = previa.get("status") or ""
        if estado_previo == "CREANDO":
            raise HTTPException(
                status_code=409,
                detail="Ese anuncio ya se está creando en este momento. Espera unos segundos y revisa «Tus campañas» antes de volver a enviarlo.",
            )
        if estado_previo == "FALLIDO":
            _fb_log.info("Reintento tras fallo previo (idempotency_key=%s)", idem)
            reserva = {"modo": "nuevo", "row_id": previa.get("id")}
        else:
            acct_prev = (previa.get("ad_account_id") or account_id).replace("act_", "")
            return {
                "ok": True,
                "duplicado": True,
                "status": estado_previo,
                "campaign_id": previa.get("campaign_id"),
                "adset_id": previa.get("adset_id"),
                "creative_id": previa.get("creative_id"),
                "ad_id": previa.get("ad_id"),
                "ads_manager_url": (
                    f"https://www.facebook.com/adsmanager/manage/campaigns"
                    f"?act={acct_prev}&selected_campaign_ids={previa.get('campaign_id')}"
                ),
                "warning": "Este anuncio ya se había creado. No se cobró dos veces.",
            }

    row_id = reserva.get("row_id", "")

    async def _marcar_fallo(detalle: str) -> None:
        if row_id:
            await update_facebook_entity(
                row_id,
                {"status": "FALLIDO", "error_detail": detalle[:1000]},
            )

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            images_b64 = [item for item in (req.images_b64 or []) if item]
            images_mime = list(req.images_mime or [])
            if not req.post_id and not images_b64:
                raise HTTPException(
                    status_code=400,
                    detail="Sube al menos una imagen para el anuncio.",
                )
            if len(images_b64) > 10:
                images_b64 = images_b64[:10]
                images_mime = images_mime[:10]
            while len(images_mime) < len(images_b64):
                images_mime.append("image/jpeg")

            if not req.city:
                raise HTTPException(
                    status_code=400,
                    detail="Debes seleccionar una ciudad para el anuncio.",
                )

            image_hashes = []
            if not req.post_id:
                for idx, image_b64 in enumerate(images_b64):
                    image_response = await _fb_request(
                        client,
                        "POST",
                        f"{account_id}/adimages",
                        token=user_token,
                        json_body={"bytes": image_b64},
                    )
                    if image_response is not None and image_response.status_code in (200, 201):
                        for value in (image_response.json().get("images") or {}).values():
                            image_hash = value.get("hash")
                            if image_hash:
                                image_hashes.append(image_hash)
                            break
                    if len(image_hashes) < idx + 1:
                        raise HTTPException(
                            status_code=502,
                            detail=_fb_friendly_error(
                                image_response.text if image_response is not None else "",
                                f"No se pudo subir la imagen {idx + 1}",
                            ),
                        )

            ad_text = (req.ad_text or "")[:2200]
            headline = (req.headline or "")[:40]
            campaign_name = (req.campaign_name or "Campaña Broquer")[:120]

            campaign_response = await _fb_request(
                client,
                "POST",
                f"{account_id}/campaigns",
                token=user_token,
                json_body={
                    "name": campaign_name,
                    "objective": "OUTCOME_ENGAGEMENT",
                    "status": "PAUSED",
                    "special_ad_categories": [],
                    "buying_type": "AUCTION",
                    "is_adset_budget_sharing_enabled": False,
                },
            )
            campaign_id = _fb_exigir_ok(campaign_response, "Error creando campaña").get("id")

            async def _cleanup(*ids) -> list:
                huerfanos = []
                for resource_id in ids:
                    if not resource_id:
                        continue
                    try:
                        cleanup_response = await _fb_request(
                            client,
                            "DELETE",
                            str(resource_id),
                            token=user_token,
                            reintentos=2,
                        )
                        if cleanup_response is None or cleanup_response.status_code not in (200, 204):
                            huerfanos.append(resource_id)
                    except Exception:
                        huerfanos.append(resource_id)
                if huerfanos:
                    _fb_log.error("No se pudieron borrar recursos de Meta: %s", huerfanos)
                return huerfanos

            def _detalle_con_huerfanos(base: str, huerfanos: list) -> str:
                if not huerfanos:
                    return base
                return (
                    f"{base} · Aviso: quedaron recursos sin borrar en tu cuenta "
                    f"({', '.join(str(item) for item in huerfanos)}). Revísalos en Ads Manager."
                )

            geo_bucket = {
                "city": "cities",
                "region": "regions",
                "neighborhood": "neighborhoods",
                "subcity": "subcities",
            }.get((req.city_type or "city").lower(), "cities")
            geo: dict = {geo_bucket: [{"key": req.city}]}
            targeting: dict = {
                "age_min": req.age_min,
                "geo_locations": geo,
                "targeting_automation": {"advantage_audience": 0},
            }
            if req.age_max and req.age_max > 0:
                targeting["age_max"] = req.age_max

            incluidos = [
                str(item).strip()
                for item in (req.custom_audience_ids or [])
                if str(item).strip()
            ]
            excluidos = [
                str(item).strip()
                for item in (req.excluded_audience_ids or [])
                if str(item).strip()
            ]
            if incluidos:
                targeting["custom_audiences"] = [{"id": item} for item in incluidos]
            if excluidos:
                targeting["excluded_custom_audiences"] = [{"id": item} for item in excluidos]

            adset_payload: dict = {
                "name": f"{campaign_name} — AdSet",
                "campaign_id": campaign_id,
                "daily_budget": daily_budget_cents,
                "billing_event": billing_event,
                "optimization_goal": optimization_goal,
                "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                "targeting": targeting,
                "status": "PAUSED",
                "promoted_object": {"page_id": page_id},
                "destination_type": "MESSENGER",
            }
            if req.duration_days and req.duration_days > 0:
                end_dt = datetime.utcnow() + timedelta(days=req.duration_days)
                adset_payload["end_time"] = end_dt.strftime("%Y-%m-%dT%H:%M:%S+0000")

            adset_response = await _fb_request(
                client,
                "POST",
                f"{account_id}/adsets",
                token=user_token,
                json_body=adset_payload,
            )
            if adset_response is None or adset_response.status_code not in (200, 201):
                huerfanos = await _cleanup(campaign_id)
                raise HTTPException(
                    status_code=502,
                    detail=_detalle_con_huerfanos(
                        _fb_friendly_error(
                            adset_response.text if adset_response is not None else "",
                            "Error creando conjunto de anuncios",
                        ),
                        huerfanos,
                    ),
                )
            adset_id = adset_response.json().get("id")

            if req.post_id:
                creative_payload: dict = {
                    "name": f"{campaign_name} — Boost",
                    "object_story_id": req.post_id,
                }
            else:
                child_attachments = []
                for image_hash in image_hashes:
                    child_attachments.append(
                        {
                            "name": headline,
                            "image_hash": image_hash,
                            "call_to_action": {
                                "type": "MESSAGE_PAGE",
                                "value": {"app_destination": "MESSENGER"},
                            },
                        }
                    )
                link_data: dict = {
                    "message": ad_text,
                    "link": f"https://www.facebook.com/{page_id}",
                    "child_attachments": child_attachments,
                    "call_to_action": {
                        "type": "MESSAGE_PAGE",
                        "value": {"app_destination": "MESSENGER"},
                    },
                }
                creative_payload = {
                    "name": f"{campaign_name} — Creative",
                    "object_story_spec": {"page_id": page_id, "link_data": link_data},
                }

            creative_response = await _fb_request(
                client,
                "POST",
                f"{account_id}/adcreatives",
                token=user_token,
                json_body=creative_payload,
            )
            if creative_response is None or creative_response.status_code not in (200, 201):
                huerfanos = await _cleanup(adset_id, campaign_id)
                raise HTTPException(
                    status_code=502,
                    detail=_detalle_con_huerfanos(
                        _fb_friendly_error(
                            creative_response.text if creative_response is not None else "",
                            "Error creando creativo",
                        ),
                        huerfanos,
                    ),
                )
            creative_id = creative_response.json().get("id")

            ad_response = await _fb_request(
                client,
                "POST",
                f"{account_id}/ads",
                token=user_token,
                json_body={
                    "name": f"{campaign_name} — Ad",
                    "adset_id": adset_id,
                    "creative": {"creative_id": creative_id},
                    "status": "PAUSED",
                },
            )
            if ad_response is None or ad_response.status_code not in (200, 201):
                huerfanos = await _cleanup(creative_id, adset_id, campaign_id)
                raise HTTPException(
                    status_code=502,
                    detail=_detalle_con_huerfanos(
                        _fb_friendly_error(
                            ad_response.text if ad_response is not None else "",
                            "Error creando anuncio",
                        ),
                        huerfanos,
                    ),
                )
            ad_id = ad_response.json().get("id")

            aviso_activacion = ""
            if target_status == "ACTIVE":
                activados: list = []
                fallo = None
                for nivel, resource_id in (
                    ("anuncio", ad_id),
                    ("conjunto", adset_id),
                    ("campaña", campaign_id),
                ):
                    activate_response = await _fb_request(
                        client,
                        "POST",
                        str(resource_id),
                        token=user_token,
                        json_body={"status": "ACTIVE"},
                    )
                    if activate_response is None or activate_response.status_code not in (200, 201):
                        fallo = (
                            nivel,
                            _fb_friendly_error(
                                activate_response.text if activate_response is not None else "",
                                f"No se pudo activar el {nivel}",
                            ),
                        )
                        break
                    activados.append(resource_id)

                if fallo:
                    for resource_id in reversed(activados):
                        try:
                            await _fb_request(
                                client,
                                "POST",
                                str(resource_id),
                                token=user_token,
                                json_body={"status": "PAUSED"},
                                reintentos=2,
                            )
                        except Exception:
                            _fb_log.error("No se pudo revertir a PAUSED: %s", resource_id)
                    target_status = "PAUSED"
                    aviso_activacion = (
                        f"{fallo[1]}. La campaña quedó creada y EN PAUSA: revísala y "
                        f"actívala desde «Tus campañas» cuando esté lista."
                    )
    except HTTPException as exc:
        await _marcar_fallo(str(exc.detail))
        raise
    except Exception as exc:
        await _marcar_fallo(f"Error inesperado: {exc}")
        raise

    await update_facebook_entity(
        row_id,
        {
            "campaign_id": campaign_id,
            "adset_id": adset_id,
            "creative_id": creative_id,
            "ad_id": ad_id,
            "status": target_status,
            "error_detail": aviso_activacion or None,
        },
    )

    acct_short = account_id.replace("act_", "")
    ads_manager_url = (
        f"https://www.facebook.com/adsmanager/manage/campaigns"
        f"?act={acct_short}&selected_campaign_ids={campaign_id}"
    )
    return {
        "ok": True,
        "status": target_status,
        "campaign_id": campaign_id,
        "adset_id": adset_id,
        "creative_id": creative_id,
        "ad_id": ad_id,
        "ads_manager_url": ads_manager_url,
        "warning": aviso_activacion,
    }
