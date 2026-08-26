"""Meta QA self-check isolated from the main application bootstrap.

This endpoint can create/toggle/delete resources, but only after three legacy
safety gates confirm an explicitly configured Meta test ad account. Architecture
work never invokes it; this module preserves the existing runtime behavior.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import io
import json
import time

import httpx
from fastapi import APIRouter, HTTPException, Request

from core.config import settings
from core.facebook_connection_store import get_facebook_meta
from core.facebook_graph import (
    _fb_friendly_error,
    _fb_get_json,
    _fb_paginate,
    _fb_request,
)
from core.facebook_insights import (
    FB_INSIGHTS_FIELDS,
    normalize_facebook_insights,
)
from core.facebook_token_lifecycle import debug_facebook_token
from core.facebook_tokens import FACEBOOK_REQUIRED_SCOPES
from core.legacy_main_config import legacy_main_settings
from routers.organizaciones import exigir_gestion_integraciones

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

router = APIRouter()

FB_APP_ID = settings.legacy_main_fb_app_id
FB_APP_SECRET = settings.legacy_main_fb_app_secret
FB_QA_ENABLED = legacy_main_settings.fb_qa_enabled
FB_QA_AD_ACCOUNT_ID = legacy_main_settings.fb_qa_ad_account_id
FB_QA_PAGE_ID = legacy_main_settings.fb_qa_page_id


def _qa_imagen_jpeg(color=(120, 150, 200), tam=(600, 600)) -> str:
    """JPEG mínimo válido en base64. 600x600 es el mínimo que acepta Meta."""
    if not PIL_AVAILABLE:
        raise HTTPException(status_code=500, detail="Pillow no disponible para generar imágenes de prueba.")
    buf = io.BytesIO()
    Image.new("RGB", tam, color).save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


async def _qa_es_cuenta_de_pruebas(
    client: httpx.AsyncClient,
    token: str,
    account_id: str,
) -> tuple:
    """(es_de_pruebas, explicación). Le pregunta a Meta, no confía en el entorno."""
    if not FB_APP_ID or not FB_APP_SECRET:
        return False, "FB_APP_ID/FB_APP_SECRET no configurados: no se puede verificar."
    try:
        cuentas = await _fb_paginate(
            client,
            f"{FB_APP_ID}/adaccounts",
            token=f"{FB_APP_ID}|{FB_APP_SECRET}",
            params={"limit": "200"},
            prefix="Error listando cuentas de prueba",
        )
    except HTTPException as exc:
        return False, f"No se pudo consultar la lista de cuentas de prueba: {exc.detail}"

    ids = set()
    for cuenta in cuentas:
        cid = str(cuenta.get("id") or cuenta.get("account_id") or "")
        if cid:
            ids.add(cid if cid.startswith("act_") else f"act_{cid}")
    if account_id in ids:
        return True, "Confirmada como cuenta de prueba de la app."
    return False, (
        f"{account_id} NO aparece en las cuentas de prueba de la app "
        f"({len(ids)} encontradas). El autodiagnóstico se niega a correr contra "
        f"una cuenta que podría ser de producción."
    )


@router.post("/facebook/qa-selfcheck")
async def facebook_qa_selfcheck(request: Request):
    """Ejercita la integración de Meta de punta a punta. Solo cuenta de pruebas."""
    user_id = await exigir_gestion_integraciones(request)

    if not FB_QA_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="El autodiagnóstico está apagado. Enciéndelo con FB_QA_ENABLED=1 "
            "y FB_QA_AD_ACCOUNT_ID apuntando a tu cuenta publicitaria de PRUEBAS.",
        )
    if not FB_QA_AD_ACCOUNT_ID:
        raise HTTPException(
            status_code=400,
            detail="Falta FB_QA_AD_ACCOUNT_ID (la cuenta de pruebas de Meta).",
        )

    try:
        body = await request.json()
    except Exception:
        body = {}
    pedidos = set(
        body.get("pasos")
        or ["tokens", "crear", "insights", "toggle", "negativos", "throttle", "limpieza"]
    )

    meta_fb = await get_facebook_meta(user_id)
    user_token = meta_fb.get("user_token", "")
    if not user_token:
        raise HTTPException(
            status_code=400,
            detail="Reconecta tu Facebook antes de correr el autodiagnóstico.",
        )

    account_id = (
        FB_QA_AD_ACCOUNT_ID
        if FB_QA_AD_ACCOUNT_ID.startswith("act_")
        else f"act_{FB_QA_AD_ACCOUNT_ID}"
    )
    page_id = FB_QA_PAGE_ID or meta_fb.get("page_id", "")

    reporte: list = []
    creados: dict = {}

    def paso(nombre: str, ok: bool, detalle="", datos=None) -> None:
        reporte.append(
            {
                "paso": nombre,
                "ok": bool(ok),
                "detalle": detalle,
                "datos": datos if datos is not None else {},
            }
        )

    async with httpx.AsyncClient(timeout=90) as client:
        es_prueba, motivo = await _qa_es_cuenta_de_pruebas(client, user_token, account_id)
        paso("candado_cuenta_de_pruebas", es_prueba, motivo, {"account_id": account_id})
        if not es_prueba:
            return {
                "ok": False,
                "abortado": True,
                "account_id": account_id,
                "motivo": motivo,
                "reporte": reporte,
            }

        if "tokens" in pedidos:
            info = await debug_facebook_token(client, user_token)
            if not info:
                paso("token_debug", False, "Meta no devolvió información del token.")
            else:
                scopes = info.get("scopes") or []
                faltantes = [scope for scope in FACEBOOK_REQUIRED_SCOPES if scope not in scopes]
                expira = info.get("expires_at") or 0
                segundos_restantes = (int(expira) - int(time.time())) if expira else -1
                larga_duracion = (expira == 0) or segundos_restantes > 7 * 24 * 3600
                paso(
                    "token_es_larga_duracion",
                    larga_duracion,
                    "El token no expira (page token) o le quedan semanas."
                    if larga_duracion
                    else f"El token expira en {max(segundos_restantes, 0) // 3600} h: NO es de larga duración.",
                    {"expires_at": expira, "segundos_restantes": segundos_restantes},
                )
                paso(
                    "token_scopes",
                    not faltantes,
                    "Todos los permisos requeridos están concedidos."
                    if not faltantes
                    else f"Faltan permisos: {', '.join(faltantes)}",
                    {"scopes": scopes, "faltantes": faltantes},
                )
                paso(
                    "token_es_valido",
                    bool(info.get("is_valid")),
                    "Meta reporta el token como válido."
                    if info.get("is_valid")
                    else "Meta reporta el token como INVÁLIDO.",
                )

        if "crear" in pedidos:
            if not page_id:
                paso(
                    "crear_anuncio",
                    False,
                    "No hay page_id: define FB_QA_PAGE_ID o conecta una página.",
                )
            else:
                nombre = f"[QA Broquer] {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}"
                try:
                    hashes = []
                    for color in [(200, 80, 80), (80, 200, 120), (80, 120, 200)]:
                        response = await _fb_request(
                            client,
                            "POST",
                            f"{account_id}/adimages",
                            token=user_token,
                            json_body={"bytes": _qa_imagen_jpeg(color)},
                        )
                        if response is not None and response.status_code in (200, 201):
                            for value in (response.json().get("images") or {}).values():
                                if value.get("hash"):
                                    hashes.append(value["hash"])
                                break
                    paso(
                        "subir_3_imagenes",
                        len(hashes) == 3,
                        f"{len(hashes)} de 3 imágenes subidas.",
                        {"hashes": hashes},
                    )

                    response = await _fb_request(
                        client,
                        "POST",
                        f"{account_id}/campaigns",
                        token=user_token,
                        json_body={
                            "name": nombre,
                            "objective": "OUTCOME_ENGAGEMENT",
                            "status": "PAUSED",
                            "special_ad_categories": [],
                            "buying_type": "AUCTION",
                        },
                    )
                    cid = (
                        response.json().get("id")
                        if response is not None and response.status_code in (200, 201)
                        else ""
                    )
                    if cid:
                        creados["campaign_id"] = cid
                    paso(
                        "crear_campana",
                        bool(cid),
                        "Campaña creada."
                        if cid
                        else _fb_friendly_error(
                            response.text if response is not None else "", "Falló"
                        ),
                        {"campaign_id": cid},
                    )

                    aid = ""
                    if cid:
                        fin = datetime.utcnow() + timedelta(days=7)
                        response = await _fb_request(
                            client,
                            "POST",
                            f"{account_id}/adsets",
                            token=user_token,
                            json_body={
                                "name": f"{nombre} — AdSet",
                                "campaign_id": cid,
                                "daily_budget": 5000,
                                "billing_event": "IMPRESSIONS",
                                "optimization_goal": "CONVERSATIONS",
                                "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                                "status": "PAUSED",
                                "promoted_object": {"page_id": page_id},
                                "destination_type": "MESSENGER",
                                "end_time": fin.strftime("%Y-%m-%dT%H:%M:%S+0000"),
                                "targeting": {
                                    "age_min": 25,
                                    "geo_locations": {"countries": ["MX"]},
                                    "targeting_automation": {"advantage_audience": 0},
                                },
                            },
                        )
                        aid = (
                            response.json().get("id")
                            if response is not None and response.status_code in (200, 201)
                            else ""
                        )
                        if aid:
                            creados["adset_id"] = aid
                        paso(
                            "crear_conjunto",
                            bool(aid),
                            "Conjunto creado."
                            if aid
                            else _fb_friendly_error(
                                response.text if response is not None else "", "Falló"
                            ),
                            {"adset_id": aid},
                        )

                    crid = ""
                    if aid and hashes:
                        hijos = [
                            {
                                "name": "QA",
                                "image_hash": image_hash,
                                "call_to_action": {
                                    "type": "MESSAGE_PAGE",
                                    "value": {"app_destination": "MESSENGER"},
                                },
                            }
                            for image_hash in hashes
                        ]
                        response = await _fb_request(
                            client,
                            "POST",
                            f"{account_id}/adcreatives",
                            token=user_token,
                            json_body={
                                "name": f"{nombre} — Creative",
                                "object_story_spec": {
                                    "page_id": page_id,
                                    "link_data": {
                                        "message": "Prueba automática de Broquer.",
                                        "link": f"https://www.facebook.com/{page_id}",
                                        "child_attachments": hijos,
                                        "call_to_action": {
                                            "type": "MESSAGE_PAGE",
                                            "value": {"app_destination": "MESSENGER"},
                                        },
                                    },
                                },
                            },
                        )
                        crid = (
                            response.json().get("id")
                            if response is not None and response.status_code in (200, 201)
                            else ""
                        )
                        if crid:
                            creados["creative_id"] = crid
                        paso(
                            "crear_creativo",
                            bool(crid),
                            "Creativo carrusel creado."
                            if crid
                            else _fb_friendly_error(
                                response.text if response is not None else "", "Falló"
                            ),
                            {"creative_id": crid},
                        )

                    adid = ""
                    if aid and crid:
                        response = await _fb_request(
                            client,
                            "POST",
                            f"{account_id}/ads",
                            token=user_token,
                            json_body={
                                "name": f"{nombre} — Ad",
                                "adset_id": aid,
                                "creative": {"creative_id": crid},
                                "status": "PAUSED",
                            },
                        )
                        adid = (
                            response.json().get("id")
                            if response is not None and response.status_code in (200, 201)
                            else ""
                        )
                        if adid:
                            creados["ad_id"] = adid
                        paso(
                            "crear_anuncio",
                            bool(adid),
                            "Anuncio creado."
                            if adid
                            else _fb_friendly_error(
                                response.text if response is not None else "", "Falló"
                            ),
                            {"ad_id": adid},
                        )

                    if adid:
                        datos = await _fb_get_json(
                            client,
                            adid,
                            token=user_token,
                            params={"fields": "status,effective_status"},
                            prefix="Error releyendo el anuncio",
                        )
                        paso(
                            "nace_en_pausa",
                            datos.get("status") == "PAUSED",
                            f"status={datos.get('status')} effective_status={datos.get('effective_status')}",
                            datos,
                        )
                except HTTPException as exc:
                    paso("crear_anuncio", False, f"Excepción: {exc.detail}")

        if "insights" in pedidos:
            try:
                filas = await _fb_paginate(
                    client,
                    f"{account_id}/insights",
                    token=user_token,
                    params={
                        "level": "campaign",
                        "fields": FB_INSIGHTS_FIELDS + ",campaign_id",
                        "date_preset": "last_30d",
                        "limit": "50",
                    },
                    prefix="Error leyendo métricas",
                )
                muestra = normalize_facebook_insights(filas[0] if filas else {})
                esperadas = {
                    "impressions",
                    "reach",
                    "spend",
                    "conversaciones",
                    "costo_conversaciones",
                    "actions",
                }
                paso(
                    "insights_llamada",
                    True,
                    f"{len(filas)} fila(s) devueltas por Meta.",
                    {"filas": len(filas)},
                )
                paso(
                    "insights_normalizados",
                    esperadas <= set(muestra.keys()),
                    "El normalizador entrega spend/reach/actions/conversaciones.",
                    {"llaves_faltantes": sorted(esperadas - set(muestra.keys()))},
                )
            except HTTPException as exc:
                paso("insights_llamada", False, str(exc.detail))

        if "toggle" in pedidos and creados.get("campaign_id"):
            cid = creados["campaign_id"]
            for objetivo in ("ACTIVE", "PAUSED"):
                errores = []
                for nivel, resource_id in (
                    ("anuncio", creados.get("ad_id")),
                    ("conjunto", creados.get("adset_id")),
                    ("campaña", cid),
                ):
                    if not resource_id:
                        continue
                    response = await _fb_request(
                        client,
                        "POST",
                        str(resource_id),
                        token=user_token,
                        json_body={"status": objetivo},
                    )
                    if response is None or response.status_code not in (200, 201):
                        errores.append(
                            f"{nivel}: "
                            + _fb_friendly_error(
                                response.text if response is not None else "", "falló"
                            )
                        )

                estados = {}
                for nivel, resource_id in (
                    ("ad", creados.get("ad_id")),
                    ("adset", creados.get("adset_id")),
                    ("campaign", cid),
                ):
                    if not resource_id:
                        continue
                    try:
                        estados[nivel] = await _fb_get_json(
                            client,
                            str(resource_id),
                            token=user_token,
                            params={"fields": "status,effective_status"},
                            prefix="Error releyendo",
                        )
                    except HTTPException as exc:
                        estados[nivel] = {"error": str(exc.detail)}

                coinciden = all(
                    value.get("status") == objetivo
                    for value in estados.values()
                    if "error" not in value
                )
                paso(
                    f"toggle_{objetivo.lower()}",
                    coinciden and not errores,
                    "Los tres niveles quedaron en el estado pedido."
                    if coinciden and not errores
                    else "; ".join(errores)
                    or "Algún nivel no quedó en el estado pedido.",
                    estados,
                )

        if "negativos" in pedidos:
            response = await _fb_request(
                client,
                "POST",
                f"{account_id}/adimages",
                token=user_token,
                json_body={"bytes": base64.b64encode(b"esto no es una imagen").decode()},
                reintentos=1,
            )
            rechazada = response is None or response.status_code not in (200, 201)
            mensaje = _fb_friendly_error(
                response.text if response is not None else "", "Imagen inválida"
            )
            paso(
                "negativo_imagen_invalida",
                rechazada,
                mensaje if rechazada else "Meta ACEPTÓ una imagen inválida (inesperado).",
            )
            paso(
                "negativo_imagen_mensaje_legible",
                rechazada and "Imagen inválida" in mensaje,
                "El error se traduce a un mensaje entendible.",
                {"mensaje": mensaje},
            )

            nombre_h = f"[QA huérfana] {datetime.now(timezone.utc):%H:%M:%S}"
            response = await _fb_request(
                client,
                "POST",
                f"{account_id}/campaigns",
                token=user_token,
                json_body={
                    "name": nombre_h,
                    "objective": "OUTCOME_ENGAGEMENT",
                    "status": "PAUSED",
                    "special_ad_categories": [],
                    "buying_type": "AUCTION",
                },
            )
            cid_h = (
                response.json().get("id")
                if response is not None and response.status_code in (200, 201)
                else ""
            )
            if cid_h:
                response2 = await _fb_request(
                    client,
                    "POST",
                    f"{account_id}/adsets",
                    token=user_token,
                    json_body={
                        "name": f"{nombre_h} — AdSet",
                        "campaign_id": cid_h,
                        "daily_budget": 99999999999,
                        "billing_event": "IMPRESSIONS",
                        "optimization_goal": "CONVERSATIONS",
                        "status": "PAUSED",
                        "targeting": {
                            "geo_locations": {"countries": ["MX"]},
                            "targeting_automation": {"advantage_audience": 0},
                        },
                    },
                    reintentos=1,
                )
                fallo_esperado = response2 is None or response2.status_code not in (200, 201)
                deleted = await _fb_request(
                    client, "DELETE", cid_h, token=user_token, reintentos=2
                )
                borrada = deleted is not None and deleted.status_code in (200, 204)
                verify = await _fb_request(
                    client,
                    "GET",
                    cid_h,
                    token=user_token,
                    params={"fields": "id"},
                    reintentos=1,
                )
                desaparecio = verify is None or verify.status_code != 200
                paso(
                    "negativo_presupuesto_excesivo",
                    fallo_esperado,
                    _fb_friendly_error(
                        response2.text if response2 is not None else "",
                        "Presupuesto excesivo",
                    )
                    if fallo_esperado
                    else "Meta aceptó un presupuesto absurdo (inesperado).",
                )
                paso(
                    "negativo_sin_huerfanos",
                    borrada and desaparecio,
                    "La campaña del intento fallido se borró y ya no existe."
                    if borrada and desaparecio
                    else f"QUEDÓ HUÉRFANA: {cid_h}. Bórrala a mano en Ads Manager.",
                    {
                        "campaign_id": cid_h,
                        "borrada": borrada,
                        "desaparecio": desaparecio,
                    },
                )
            else:
                paso(
                    "negativo_presupuesto_excesivo",
                    False,
                    "No se pudo crear la campaña de prueba para el caso negativo.",
                )

            try:
                promocionables = [
                    item.get("id")
                    for item in await _fb_paginate(
                        client,
                        f"{account_id}/promote_pages",
                        token=user_token,
                        params={"fields": "id", "limit": "100"},
                        prefix="promote_pages",
                    )
                ]
                detecta = bool(promocionables) and page_id in promocionables
                paso(
                    "negativo_pagina_cuenta_correcta",
                    True,
                    f"La cuenta puede anunciar {len(promocionables)} página(s); "
                    f"la configurada {'SÍ' if detecta else 'NO'} está entre ellas.",
                    {"promote_pages": promocionables, "page_id": page_id},
                )
            except HTTPException as exc:
                paso("negativo_pagina_cuenta_correcta", False, str(exc.detail))

        if "limpieza" in pedidos and creados.get("campaign_id"):
            cid = creados["campaign_id"]
            deleted = await _fb_request(
                client, "DELETE", cid, token=user_token, reintentos=3
            )
            borrada = deleted is not None and deleted.status_code in (200, 204)
            verify = await _fb_request(
                client,
                "GET",
                cid,
                token=user_token,
                params={"fields": "id"},
                reintentos=1,
            )
            desaparecio = verify is None or verify.status_code != 200
            paso(
                "limpieza_campana_borrada",
                borrada and desaparecio,
                "La campaña de prueba se borró y ya no existe en Meta."
                if borrada and desaparecio
                else f"NO se pudo borrar {cid}. Bórrala a mano en Ads Manager.",
                {
                    "campaign_id": cid,
                    "borrada": borrada,
                    "ya_no_existe": desaparecio,
                },
            )

    if "throttle" in pedidos:
        resultado = await _qa_probar_backoff()
        paso("throttle_backoff_429", resultado["ok"], resultado["detalle"], resultado)

    fallidos = [item for item in reporte if not item["ok"]]
    return {
        "ok": not fallidos,
        "account_id": account_id,
        "page_id": page_id,
        "total": len(reporte),
        "fallidos": len(fallidos),
        "resumen": (
            "Todo en orden."
            if not fallidos
            else "Fallaron: " + ", ".join(item["paso"] for item in fallidos)
        ),
        "recursos_creados": creados,
        "reporte": reporte,
    }


async def _qa_probar_backoff() -> dict:
    """Comprueba que _fb_request se recupera de un 429 sin salir a internet."""
    intentos = {"n": 0}

    def responder(request: httpx.Request) -> httpx.Response:
        intentos["n"] += 1
        if intentos["n"] <= 2:
            return httpx.Response(
                429,
                headers={
                    "Retry-After": "0",
                    "X-Business-Use-Case-Usage": json.dumps(
                        {
                            "1": [
                                {
                                    "type": "ads_management",
                                    "call_count": 100,
                                    "total_cputime": 100,
                                    "total_time": 100,
                                    "estimated_time_to_regain_access": 0,
                                }
                            ]
                        }
                    ),
                },
                json={
                    "error": {
                        "message": "User request limit reached",
                        "code": 17,
                        "type": "OAuthException",
                    }
                },
            )
        return httpx.Response(200, json={"data": [], "ok": True})

    inicio = time.monotonic()
    try:
        transporte = httpx.MockTransport(responder)
        async with httpx.AsyncClient(transport=transporte) as client:
            response = await _fb_request(
                client,
                "GET",
                "me/adaccounts",
                token="fake",
                espera_base=0.05,
                espera_max=0.2,
            )
    except Exception as exc:
        return {
            "ok": False,
            "detalle": f"El wrapper lanzó excepción: {exc}",
            "intentos": intentos["n"],
        }

    duracion = time.monotonic() - inicio
    ok = response is not None and response.status_code == 200 and intentos["n"] == 3
    return {
        "ok": ok,
        "detalle": (
            f"Se recuperó del 429 tras {intentos['n']} intentos ({duracion:.2f}s) y terminó en 200."
            if ok
            else f"No se recuperó: {intentos['n']} intentos, status final {getattr(response, 'status_code', 'ninguno')}."
        ),
        "intentos": intentos["n"],
        "status_final": getattr(response, "status_code", None),
        "segundos": round(duracion, 3),
    }
