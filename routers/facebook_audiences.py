"""Create Facebook custom and lookalike audiences from Broquer CRM data."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
import re

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.config import settings
from core.database import get_rows, post_rows
from core.facebook_connection_store import get_facebook_meta
from core.facebook_graph import _fb_exigir_ok, _fb_friendly_error, _fb_request
from core.facebook_persistence import facebook_table_missing, warn_facebook_migration
from routers.organizaciones import exigir_gestion_integraciones, get_org_id_for_user

router = APIRouter()
_log = logging.getLogger("broquer.facebook")


def _hash_meta(valor: str) -> str:
    """SHA-256 in lowercase, as Meta requires for customer matching."""
    if not valor:
        return ""
    return hashlib.sha256(valor.strip().lower().encode("utf-8")).hexdigest()


def _normaliza_email(email: str) -> str:
    """Validate and hash an email using the historical matching contract."""
    email = (email or "").strip().lower()
    if email.count("@") != 1:
        return ""
    local, _, dominio = email.partition("@")
    if not local or "." not in dominio:
        return ""
    if not dominio.split(".")[0] or len(dominio.rsplit(".", 1)[-1]) < 2:
        return ""
    return _hash_meta(email)


def _normaliza_telefono(tel: str, lada_pais: str = "52") -> str:
    """Normalize a phone to Meta's digits-only E.164 form, then hash it."""
    digitos = re.sub(r"\D", "", tel or "")
    if not digitos:
        return ""
    if len(digitos) == 10:
        digitos = lada_pais + digitos
    elif len(digitos) == 13 and digitos.startswith(lada_pais + "1"):
        digitos = lada_pais + digitos[3:]
    if len(digitos) < 11 or len(digitos) > 15:
        return ""
    return _hash_meta(digitos)


class FbAudienceRequest(BaseModel):
    nombre: str = ""
    solo_potenciales: bool = False
    etiquetas: list = []
    descripcion: str = ""


class FbLookalikeRequest(BaseModel):
    origin_audience_id: str
    nombre: str = ""
    ratio: float = 0.01
    pais: str = "MX"


async def _fb_guardar_audiencia(user_id: str, org_id, datos: dict) -> None:
    """Persist audience bookkeeping best-effort; never fail the primary Meta operation."""
    if not settings.supabase_url or not settings.supabase_service_key:
        return
    try:
        try:
            await post_rows(
                "fb_audiences",
                {"user_id": user_id, "org_id": org_id, **datos},
                prefer="resolution=merge-duplicates,return=minimal",
                timeout=10,
                accepted_statuses=(200, 201, 204),
            )
        except httpx.HTTPStatusError as exc:
            if facebook_table_missing(exc.response):
                warn_facebook_migration("guardar público", exc.response)
            else:
                _log.error(
                    "No se pudo guardar el público: %s %s",
                    exc.response.status_code,
                    (exc.response.text or "")[:200],
                )
    except Exception as exc:
        _log.error("Error guardando el público: %s", exc)


@router.post("/facebook/audiences/from-contacts")
async def facebook_audience_from_contacts(req: FbAudienceRequest, request: Request):
    """Create a Meta custom audience from hashed CRM contacts."""
    user_id = await exigir_gestion_integraciones(request)
    meta_fb = await get_facebook_meta(user_id)
    user_token = meta_fb.get("user_token", "")
    account_id = meta_fb.get("ad_account_id", "")
    if not user_token or not account_id:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook desde tu perfil.")
    account_id = account_id if account_id.startswith("act_") else f"act_{account_id}"

    org_id = await get_org_id_for_user(user_id)
    filtros = {
        "select": "id,nombre,email,telefono,wa,etiquetas,es_potencial",
        "limit": "5000",
    }
    if org_id:
        filtros["org_id"] = f"eq.{org_id}"
    else:
        filtros["user_id"] = f"eq.{user_id}"
    if req.solo_potenciales:
        filtros["es_potencial"] = "eq.true"

    try:
        contactos = await get_rows("contactos", filtros, timeout=30)
    except httpx.HTTPStatusError:
        raise HTTPException(status_code=502, detail="No se pudieron leer tus contactos.")

    etiquetas_filtro = {
        str(etiqueta).strip().lower()
        for etiqueta in (req.etiquetas or [])
        if str(etiqueta).strip()
    }
    if etiquetas_filtro:
        contactos = [
            contacto
            for contacto in contactos
            if etiquetas_filtro
            & {str(etiqueta).lower() for etiqueta in (contacto.get("etiquetas") or [])}
        ]

    datos: list = []
    for contacto in contactos:
        h_mail = _normaliza_email(contacto.get("email") or "")
        h_tel = _normaliza_telefono(contacto.get("telefono") or contacto.get("wa") or "")
        if h_mail or h_tel:
            datos.append([h_mail, h_tel])

    if not datos:
        raise HTTPException(
            status_code=400,
            detail="Ninguno de tus contactos tiene correo o teléfono utilizable. "
            "Completa esos datos en el CRM antes de crear el público.",
        )

    nombre = (req.nombre or f"Broquer · Contactos {datetime.now(timezone.utc):%Y-%m-%d}")[:100]

    async with httpx.AsyncClient(timeout=60) as client:
        response = await _fb_request(
            client,
            "POST",
            f"{account_id}/customaudiences",
            token=user_token,
            json_body={
                "name": nombre,
                "subtype": "CUSTOM",
                "description": (req.descripcion or "Contactos del CRM de Broquer")[:200],
                "customer_file_source": "USER_PROVIDED_ONLY",
            },
        )
        if response is None or response.status_code not in (200, 201):
            texto = response.text if response is not None else ""
            if "2654" in texto or "terms of service" in texto.lower():
                raise HTTPException(
                    status_code=400,
                    detail="Falta aceptar las Condiciones de Públicos Personalizados de Meta. "
                    "Entra a business.facebook.com → Configuración del negocio → "
                    "Cuentas publicitarias → tu cuenta → Condiciones de públicos "
                    "personalizados, acéptalas y vuelve a intentar.",
                )
            raise HTTPException(
                status_code=502,
                detail=_fb_friendly_error(texto, "Error creando el público"),
            )
        audience_id = response.json().get("id", "")

        subidos = 0
        fallos = []
        for i in range(0, len(datos), 5000):
            lote = datos[i : i + 5000]
            upload_response = await _fb_request(
                client,
                "POST",
                f"{audience_id}/users",
                token=user_token,
                json_body={"payload": {"schema": ["EMAIL", "PHONE"], "data": lote}},
                timeout=90,
            )
            if upload_response is not None and upload_response.status_code in (200, 201):
                subidos += len(lote)
            else:
                fallos.append(
                    _fb_friendly_error(
                        upload_response.text if upload_response is not None else "",
                        f"Lote {i // 5000 + 1}",
                    )
                )

        if not subidos:
            await _fb_request(
                client,
                "DELETE",
                audience_id,
                token=user_token,
                reintentos=2,
            )
            raise HTTPException(
                status_code=502,
                detail="No se pudo subir ningún contacto a Meta: "
                + ("; ".join(fallos) or "error desconocido"),
            )

    await _fb_guardar_audiencia(
        user_id,
        org_id,
        {
            "ad_account_id": account_id,
            "audience_id": audience_id,
            "nombre": nombre,
            "tipo": "CUSTOM",
            "contactos_enviados": subidos,
        },
    )

    aviso = ""
    if subidos < 100:
        aviso = (
            f"Solo se subieron {subidos} contactos. Meta necesita alrededor de 100 "
            f"coincidencias para que un público se pueda usar en un anuncio; "
            f"este puede quedar inutilizable hasta que crezca tu cartera."
        )
    elif fallos:
        aviso = "Algunos lotes fallaron: " + "; ".join(fallos)

    return {
        "ok": True,
        "audience_id": audience_id,
        "nombre": nombre,
        "contactos_enviados": subidos,
        "contactos_totales": len(datos),
        "warning": aviso,
        "nota": "Meta tarda entre 30 minutos y varias horas en procesar el público.",
    }


@router.post("/facebook/audiences/lookalike")
async def facebook_audience_lookalike(req: FbLookalikeRequest, request: Request):
    """Create a Meta lookalike audience from an existing audience."""
    user_id = await exigir_gestion_integraciones(request)
    meta_fb = await get_facebook_meta(user_id)
    user_token = meta_fb.get("user_token", "")
    account_id = meta_fb.get("ad_account_id", "")
    if not user_token or not account_id:
        raise HTTPException(status_code=400, detail="Reconecta tu Facebook desde tu perfil.")
    account_id = account_id if account_id.startswith("act_") else f"act_{account_id}"

    if not req.origin_audience_id:
        raise HTTPException(status_code=400, detail="Falta el público de origen.")
    ratio = req.ratio if 0.01 <= req.ratio <= 0.20 else 0.01
    pais = (req.pais or "MX").upper()[:2]
    nombre = (req.nombre or f"Broquer · Similar {int(ratio * 100)}% {pais}")[:100]

    async with httpx.AsyncClient(timeout=60) as client:
        response = await _fb_request(
            client,
            "POST",
            f"{account_id}/customaudiences",
            token=user_token,
            json_body={
                "name": nombre,
                "subtype": "LOOKALIKE",
                "origin_audience_id": req.origin_audience_id,
                "lookalike_spec": {"ratio": ratio, "country": pais, "type": "similarity"},
            },
        )
    datos = _fb_exigir_ok(response, "Error creando el público similar")
    audience_id = datos.get("id", "")

    await _fb_guardar_audiencia(
        user_id,
        await get_org_id_for_user(user_id),
        {
            "ad_account_id": account_id,
            "audience_id": audience_id,
            "nombre": nombre,
            "tipo": "LOOKALIKE",
            "origen_id": req.origin_audience_id,
            "pais": pais,
            "ratio": ratio,
        },
    )

    return {
        "ok": True,
        "audience_id": audience_id,
        "nombre": nombre,
        "ratio": ratio,
        "pais": pais,
        "nota": "Meta tarda entre 6 y 24 horas en construir un público similar. "
        "Hasta entonces no lo podrás usar en un anuncio.",
    }
