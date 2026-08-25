"""Server-side Facebook Lead Ads ingestion and CRM contact persistence."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import uuid as _uuid

import httpx

from core.config import settings
from core.database import get_rows, patch_rows, post_rows
from core.facebook_graph import _fb_friendly_error, _fb_request
from core.facebook_persistence import facebook_table_missing, warn_facebook_migration
from core.facebook_secrets import decrypt_facebook_secret


_log = logging.getLogger("broquer.facebook")

FACEBOOK_LEAD_FIELDS = {
    "full_name": "nombre",
    "first_name": "_nombre_pila",
    "last_name": "_apellido",
    "email": "email",
    "phone_number": "telefono",
    "company_name": "empresa",
    "city": "mpio",
    "street_address": "calle",
    "post_code": "cp",
}


async def find_facebook_page_owner(page_id: str) -> dict:
    """Find the Broquer user/company that owns a connected Facebook page."""
    if not page_id or not settings.supabase_url or not settings.supabase_service_key:
        return {}
    try:
        try:
            rows = await get_rows(
                "user_integrations",
                {
                    "provider": "eq.facebook",
                    "select": "user_id,org_id,api_key,meta",
                    "meta": f"like.*{page_id}*",
                    "limit": "20",
                },
                timeout=15,
            )
        except httpx.HTTPStatusError:
            rows = []
        if not rows:
            try:
                rows = await get_rows(
                    "user_integrations",
                    {
                        "provider": "eq.facebook",
                        "select": "user_id,org_id,api_key,meta",
                        "limit": "500",
                    },
                    timeout=15,
                )
            except httpx.HTTPStatusError:
                rows = []
    except Exception as exc:
        _log.error("Error buscando al dueño de la página %s: %s", page_id, exc)
        return {}

    for row in rows:
        meta_raw = row.get("meta") or "{}"
        try:
            meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
        except Exception:
            continue
        if meta.get("page_id") == page_id:
            return {
                "user_id": row.get("user_id"),
                "org_id": row.get("org_id"),
                "page_token": decrypt_facebook_secret(row.get("api_key", "")),
                "meta": meta,
            }
    return {}


async def process_facebook_lead(value: dict) -> None:
    """Download one Meta Lead Ad lead and persist it as a CRM prospect.

    This deliberately preserves the historical fail-soft background-task
    contract: failures are recorded/logged and do not escape to the webhook.
    """
    leadgen_id = str(value.get("leadgen_id") or "")
    page_id = str(value.get("page_id") or "")
    if not leadgen_id:
        return

    ledger = {
        "leadgen_id": leadgen_id,
        "page_id": page_id,
        "form_id": str(value.get("form_id") or ""),
        "ad_id": str(value.get("ad_id") or ""),
        "adset_id": str(value.get("adgroup_id") or value.get("adset_id") or ""),
        "campaign_id": str(value.get("campaign_id") or ""),
        "payload": value,
        "procesado": False,
    }

    async def _annotate(extra: dict) -> None:
        try:
            try:
                await post_rows(
                    "fb_leads_recibidos",
                    {**ledger, **extra},
                    prefer="return=minimal",
                    timeout=10,
                    accepted_statuses=(200, 201, 204),
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 409 and not facebook_table_missing(exc.response):
                    _log.error(
                        "No se pudo anotar el lead %s: %s %s",
                        leadgen_id,
                        exc.response.status_code,
                        (exc.response.text or "")[:200],
                    )
        except Exception as exc:
            _log.error("Error anotando el lead %s: %s", leadgen_id, exc)

    try:
        try:
            previous_rows = await get_rows(
                "fb_leads_recibidos",
                {"leadgen_id": f"eq.{leadgen_id}", "select": "id,procesado", "limit": "1"},
                timeout=10,
            )
        except httpx.HTTPStatusError as exc:
            if facebook_table_missing(exc.response):
                warn_facebook_migration("procesar lead", exc.response)
            previous_rows = []
        if previous_rows and (previous_rows[0] or {}).get("procesado"):
            _log.info("Lead %s ya procesado; se ignora el reenvío.", leadgen_id)
            return
    except Exception:
        pass

    owner = await find_facebook_page_owner(page_id)
    if not owner.get("user_id"):
        _log.warning(
            "Llegó un lead de la página %s pero ningún usuario de "
            "Broquer la tiene conectada.",
            page_id,
        )
        await _annotate({"error_detail": "Página no conectada a ningún usuario de Broquer."})
        return

    user_id = owner["user_id"]
    org_id = owner.get("org_id")
    page_token = owner.get("page_token", "")
    ledger["user_id"] = user_id
    ledger["org_id"] = org_id

    if not page_token:
        await _annotate({"error_detail": "No hay token de página para leer el lead."})
        return

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await _fb_request(
                client,
                "GET",
                leadgen_id,
                token=page_token,
                params={
                    "fields": "id,created_time,field_data,ad_id,adset_id,campaign_id,form_id"
                },
            )
        if response is None or response.status_code != 200:
            detail = _fb_friendly_error(
                response.text if response is not None else "",
                "No se pudo leer el lead",
            )
            _log.error("Lead %s: %s", leadgen_id, detail)
            await _annotate({"error_detail": detail})
            return
        lead = response.json() or {}
    except Exception as exc:
        await _annotate({"error_detail": f"Error leyendo el lead: {exc}"})
        return

    fields: dict = {}
    extras: list = []
    for field in lead.get("field_data") or []:
        field_name = (field.get("name") or "").lower()
        values = field.get("values") or []
        value_text = str(values[0]).strip() if values else ""
        if not value_text:
            continue
        destination = FACEBOOK_LEAD_FIELDS.get(field_name)
        if destination:
            fields[destination] = value_text
        else:
            label = (field.get("name") or "").replace("_", " ").capitalize()
            extras.append(f"{label}: {value_text}")

    name = fields.pop("nombre", "") or " ".join(
        item
        for item in (fields.pop("_nombre_pila", ""), fields.pop("_apellido", ""))
        if item
    ).strip()
    fields.pop("_nombre_pila", None)
    fields.pop("_apellido", None)

    phone = fields.get("telefono", "")
    email = fields.get("email", "")
    if not name and not phone and not email:
        await _annotate({"error_detail": "El formulario no traía nombre, teléfono ni correo."})
        return

    notes = ["Llegó por un anuncio de Facebook (Lead Ad)."]
    if lead.get("created_time"):
        notes.append(f"Fecha del formulario: {lead['created_time']}")
    if lead.get("campaign_id"):
        notes.append(f"Campaña: {lead['campaign_id']}")
    notes.extend(extras)

    now = datetime.now(timezone.utc).isoformat()
    contact = {
        "id": str(_uuid.uuid4()),
        "user_id": user_id,
        "org_id": org_id,
        "nombre": name or "Prospecto de Facebook",
        "tipo": "otro",
        "es_potencial": True,
        "fuente": "Facebook Lead Ads",
        "etiquetas": ["Facebook", "Lead Ad"],
        "notas": "\n".join(notes),
        "created_at": now,
        "updated_at": now,
        **{key: val for key, val in fields.items() if val},
    }
    if phone and not contact.get("wa"):
        contact["wa"] = phone

    try:
        filters = {"select": "id,nombre,email,telefono", "limit": "1"}
        if org_id:
            filters["org_id"] = f"eq.{org_id}"
        else:
            filters["user_id"] = f"eq.{user_id}"
        if phone:
            filters["telefono"] = f"eq.{phone}"
        elif email:
            filters["email"] = f"eq.{email}"

        async with httpx.AsyncClient(timeout=15):
            try:
                existing_rows = await get_rows("contactos", filters, timeout=15)
            except httpx.HTTPStatusError:
                existing_rows = []
            existing = existing_rows[0] if existing_rows else None

            if existing:
                try:
                    await patch_rows(
                        "contactos",
                        {"id": f"eq.{existing['id']}"},
                        {"es_potencial": True, "updated_at": now},
                        timeout=15,
                    )
                except httpx.HTTPStatusError:
                    pass
                await _annotate(
                    {
                        "procesado": True,
                        "contacto_id": existing["id"],
                        "error_detail": "Contacto ya existía; se marcó como potencial.",
                    }
                )
                _log.info("Lead %s emparejado con el contacto %s", leadgen_id, existing["id"])
                return

            try:
                await post_rows(
                    "contactos",
                    {key: val for key, val in contact.items() if val not in ("", None, [])},
                    prefer="return=minimal",
                    timeout=15,
                    accepted_statuses=(200, 201, 204),
                )
            except httpx.HTTPStatusError as exc:
                await _annotate(
                    {
                        "error_detail": (
                            f"No se pudo crear el contacto: {(exc.response.text or '')[:200]}"
                        )
                    }
                )
                return
    except Exception as exc:
        await _annotate({"error_detail": f"Error guardando el contacto: {exc}"})
        return

    await _annotate({"procesado": True, "contacto_id": contact["id"]})
    _log.info(
        "Lead %s guardado como contacto %s del usuario %s",
        leadgen_id,
        contact["id"],
        user_id,
    )
