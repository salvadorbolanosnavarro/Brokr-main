"""Bridge WhatsApp contacts to the canonical Broquer CRM contact records."""
from __future__ import annotations

from datetime import datetime, timezone
import logging

from routers.organizaciones import get_org_context
from routers.whatsapp_data import sb_get, sb_patch, sb_post
from routers.whatsapp_time import hora_local
from routers.whatsapp_utils import normaliza_mx


log = logging.getLogger("broquer.whatsapp2")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def perfil_agente(user_id: str) -> dict:
    nombre, zona = "", ""
    try:
        rows = await sb_get(
            "usuarios",
            {"id": f"eq.{user_id}", "select": "nombre_publico,zona_cobertura", "limit": "1"},
        )
        if rows:
            nombre = (rows[0].get("nombre_publico") or "").strip()
            zona = (rows[0].get("zona_cobertura") or "").strip()
    except Exception:
        pass
    return {"nombre": nombre or "tu asesor inmobiliario", "zona": zona}


async def crear_contacto_crm(user_id: str, wa_id: str, nombre: str | None) -> str | None:
    contacto_id = f"c_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    telefono = normaliza_mx(wa_id)
    ctx_org = await get_org_context(user_id)
    org_id = (ctx_org or {}).get("org_id")
    fila = {
        "id": contacto_id,
        "user_id": user_id,
        "org_id": org_id,
        "nombre": (nombre or telefono or "Prospecto de WhatsApp").upper(),
        "telefono": telefono,
        "wa": telefono,
        "tipo": "comprador",
        "fuente": "WhatsApp",
        "notas": "Prospecto creado automáticamente por WhatsApp.",
        "es_potencial": True,
        "etiquetas": ["WhatsApp"],
        "operaciones": [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    creado = await sb_post("contactos", fila)
    if not creado:
        log.error("No se pudo crear el Contacto en el CRM para wa_id=%s (user=%s)", wa_id, user_id)
        return None
    return contacto_id


async def sincronizar_contacto_crm(
    user_id: str,
    contacto_wa2: dict,
    resultado_ia: dict | None = None,
) -> None:
    crm_id = contacto_wa2.get("contacto_crm_id")
    if not crm_id or not resultado_ia:
        return
    try:
        cambios = {"updated_at": _now()}
        busca = (resultado_ia.get("busca") or "").strip().lower()
        if "rent" in busca:
            cambios["tipo"] = "arrendatario"
        elif busca:
            cambios["tipo"] = "comprador"
        nombre_chat_crm = (resultado_ia.get("nombre") or "").strip()
        if nombre_chat_crm:
            cambios["nombre"] = nombre_chat_crm.upper()
        nota = resultado_ia.get("nota") or resultado_ia.get("resumen")
        if nota:
            rows = await sb_get("contactos", {"id": f"eq.{crm_id}", "select": "notas", "limit": "1"})
            previas = (rows[0].get("notas") or "") if rows else ""
            fecha = hora_local().strftime("%d/%m %H:%M")
            cambios["notas"] = (previas + f"\n[{fecha} · WhatsApp] {nota}").strip()

        renglones = []
        if contacto_wa2.get("temperatura"):
            renglones.append(f"Temperatura: {contacto_wa2['temperatura']}")
        if contacto_wa2.get("score") is not None:
            renglones.append(f"Score: {contacto_wa2['score']}")
        if contacto_wa2.get("presupuesto"):
            renglones.append(f"Presupuesto: {contacto_wa2['presupuesto']}")
        if contacto_wa2.get("forma_pago"):
            renglones.append(f"Forma de pago: {contacto_wa2['forma_pago']}")
        if contacto_wa2.get("busca"):
            renglones.append(f"Busca: {contacto_wa2['busca']}")
        if contacto_wa2.get("resumen"):
            renglones.append(f"Resumen: {contacto_wa2['resumen']}")
        if renglones:
            cambios["descripcion_privada"] = "\n".join(renglones)

        await sb_patch("contactos", {"id": f"eq.{crm_id}"}, cambios)
    except Exception as exc:
        log.warning("No se pudo sincronizar el Contacto %s del CRM: %s", crm_id, exc)
