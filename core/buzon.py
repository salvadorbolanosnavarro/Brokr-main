"""Buzón: registro único de leads y asignación automática.

Todo lo que entra (WhatsApp, formulario del sitio, Bolsa, Zapier/EasyBroker,
lead capturado a mano) pasa por ``registrar_lead``: busca o crea el contacto
sin duplicar (teléfono a 10 dígitos o correo), liga inmueble y fuente, aplica
la regla de asignación de la organización y avisa al agente.

Depende de: migracion-fase4-buzon.sql.
"""
from __future__ import annotations

import logging
import random
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import httpx

from core.database import call_service_rpc, get_rows, patch_rows, post_rows

log = logging.getLogger("broquer.buzon")

CANALES = {
    "whatsapp": "WhatsApp",
    "sitio": "Sitio web",
    "bolsa": "Bolsa Broquer",
    "zapier": "Zapier",
    "easybroker": "EasyBroker",
    "telefono": "Llamada",
    "manual": "Captura manual",
    "meta": "Meta Lead Ads",
    "portal": "Portal inmobiliario",
    "correo": "Correo",
}
ESTADOS = ("sin_atender", "atendida", "archivada", "spam")
MODOS = ("manual", "agente_inmueble", "ruleta", "guardias")


def ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def tel10(v: Any) -> str:
    d = re.sub(r"\D", "", str(v or ""))
    if len(d) > 10:
        d = d[-10:]
    return d if len(d) == 10 else ""


def nuevo_id_contacto() -> str:
    return f"c_{int(datetime.now(timezone.utc).timestamp() * 1000)}{random.randint(100, 999)}"


def nuevo_token() -> str:
    return secrets.token_urlsafe(24)


# ── Asignación ──────────────────────────────────────────────────────────────
def _en_guardia(g: dict, momento: datetime) -> bool:
    dia = (momento.weekday() + 1) % 7      # Python: lunes=0 → guardias: domingo=0
    if int(g.get("dia", -1)) != dia:
        return False
    hora = momento.strftime("%H:%M:%S")
    ini, fin = str(g.get("hora_inicio") or "00:00:00"), str(g.get("hora_fin") or "23:59:59")
    if len(ini) == 5:
        ini += ":00"
    if len(fin) == 5:
        fin += ":00"
    return ini <= hora <= fin if ini <= fin else (hora >= ini or hora <= fin)   # guardia que cruza medianoche


def elegir_asignado(regla: Optional[dict], miembros_activos: List[str], propiedad: Optional[dict],
                    guardias: List[dict], momento: datetime) -> Tuple[Optional[str], Optional[int]]:
    """(usuario asignado o None, nuevo puntero de ruleta o None). Pura: testeable."""
    modo = (regla or {}).get("modo") or "manual"
    activos = [m for m in miembros_activos if m]
    if modo == "agente_inmueble" and propiedad:
        for cand in (propiedad.get("asignado_a"), propiedad.get("user_id")):
            if cand in activos:
                return cand, None
        return None, None
    if modo == "ruleta":
        lista = [u for u in (regla.get("ruleta_usuarios") or []) if u in activos]
        if not lista:
            return None, None
        i = (int(regla.get("ruleta_ultimo", -1)) + 1) % len(lista)
        return lista[i], i
    if modo == "guardias":
        de_guardia = []
        for g in guardias:
            if g.get("user_id") in activos and _en_guardia(g, momento) and g["user_id"] not in de_guardia:
                de_guardia.append(g["user_id"])
        if not de_guardia:
            return None, None
        i = (int((regla or {}).get("ruleta_ultimo", -1)) + 1) % len(de_guardia)
        return de_guardia[i], i
    return None, None


async def regla_de(org_id: str) -> dict:
    filas = await get_rows("buzon_reglas", {"org_id": f"eq.{org_id}", "select": "*", "limit": "1"})
    if filas:
        return filas[0]
    try:
        filas = await post_rows("buzon_reglas", {"org_id": org_id, "modo": "manual"})
    except httpx.HTTPStatusError:
        filas = await get_rows("buzon_reglas", {"org_id": f"eq.{org_id}", "select": "*", "limit": "1"})
    return filas[0] if filas else {"org_id": org_id, "modo": "manual"}


async def miembros_activos(org_id: str) -> List[str]:
    filas = await get_rows("organizacion_miembros", {"org_id": f"eq.{org_id}", "activo": "eq.true", "select": "user_id"})
    return [f["user_id"] for f in filas]


async def asignar_automatico(org_id: str, propiedad: Optional[dict]) -> Optional[str]:
    regla = await regla_de(org_id)
    modo = regla.get("modo") or "manual"
    if modo == "manual":
        return None
    activos = await miembros_activos(org_id)
    guardias = []
    if modo == "guardias":
        guardias = await get_rows("buzon_guardias", {"org_id": f"eq.{org_id}", "select": "user_id,dia,hora_inicio,hora_fin"})
    try:
        tz = ZoneInfo(regla.get("zona_horaria") or "America/Mexico_City")
    except Exception:
        tz = ZoneInfo("America/Mexico_City")
    elegido, puntero = elegir_asignado(regla, activos, propiedad, guardias, datetime.now(tz))
    if puntero is not None:
        await patch_rows("buzon_reglas", {"org_id": f"eq.{org_id}"}, {"ruleta_ultimo": puntero, "updated_at": ahora_iso()})
    return elegido


async def avisar_asignacion(user_id: Optional[str], lead: dict) -> None:
    """Push a la app del agente. El aviso en el web es el contador del menú."""
    if not user_id:
        return
    try:
        from push import enviar_push
        canal = CANALES.get(lead.get("canal"), lead.get("canal") or "")
        await enviar_push(user_id, "Nuevo lead asignado",
                          f"{lead.get('nombre') or 'Sin nombre'} · {canal}",
                          {"tipo": "buzon", "url": f"buzon.html?id={lead.get('id')}"})
    except Exception as e:   # un push fallido nunca tumba el registro del lead
        log.warning("push de asignación falló: %s", e)


# ── Registro ───────────────────────────────────────────────────────────────
async def _fuente(org_id: str, nombre: str) -> Optional[dict]:
    try:
        from routers.crm import fuente_para
        return await fuente_para(org_id, nombre)
    except Exception as e:
        log.info("fuente no disponible (%s): %s", nombre, e)
        return None


async def contacto_para(org_id: str, user_id: str, nombre: str, telefono: str, email: str,
                        fuente: Optional[dict], canal: str) -> Optional[str]:
    t, m = tel10(telefono), (email or "").strip().lower()
    if t or m:
        try:
            cid = await call_service_rpc("bk_buscar_contacto", {"p_org": org_id, "p_tel10": t or None, "p_email": m or None})
            if cid:
                return cid
        except httpx.HTTPStatusError as e:
            log.warning("bk_buscar_contacto no disponible: %s", e.response.text[:120])
    if not (nombre or t or m):
        return None
    ahora = ahora_iso()
    fila = {
        "id": nuevo_id_contacto(), "user_id": user_id, "org_id": org_id,
        "nombre": (nombre or telefono or email or "Sin nombre").upper()[:120],
        "telefono": telefono or None, "email": m or None,
        "fuente": (fuente or {}).get("nombre") or CANALES.get(canal), "fuente_id": (fuente or {}).get("id"),
        "es_potencial": True, "estatus": "nuevo", "tipo": "comprador",
        "etiquetas": [], "operaciones": [], "created_at": ahora, "updated_at": ahora,
    }
    try:
        creados = await post_rows("contactos", fila)
    except httpx.HTTPStatusError:
        fila.pop("fuente_id", None)
        creados = await post_rows("contactos", fila)
    return (creados[0] if creados else fila)["id"]


async def registrar_lead(*, org_id: str, user_id: str, canal: str, nombre: str = "", telefono: str = "",
                         email: str = "", mensaje: str = "", fuente: str = "", propiedad_id: Optional[str] = None,
                         referencia: Optional[str] = None, contacto_id: Optional[str] = None,
                         datos: Optional[dict] = None, asignado_a: Optional[str] = None) -> dict:
    """Crea (o reabre) el lead en el Buzón. Devuelve la fila."""
    canal = (canal or "manual").strip().lower()[:30]
    ahora = ahora_iso()

    propiedad = None
    if propiedad_id:
        filas = await get_rows("propiedades", {"id": f"eq.{propiedad_id}", "select": "id,user_id,org_id,asignado_a,titulo"})
        if filas and (filas[0].get("org_id") in (org_id, None)):
            propiedad = filas[0]
        else:
            propiedad_id = None

    fte = await _fuente(org_id, fuente or CANALES.get(canal, canal))

    if referencia:
        previo = await get_rows("buzon_leads", {"org_id": f"eq.{org_id}", "canal": f"eq.{canal}",
                                                "referencia": f"eq.{referencia}", "select": "*", "limit": "1"})
        if previo:
            lead = previo[0]
            cambios = {"ultimo_mensaje_en": ahora, "updated_at": ahora}
            if mensaje:
                cambios["mensaje"] = mensaje[:2000]
            if lead.get("estado") in ("atendida", "archivada"):
                cambios["estado"] = "sin_atender"        # un mensaje nuevo reabre la conversación
            res = await patch_rows("buzon_leads", {"id": f"eq.{lead['id']}"}, cambios, prefer="return=representation")
            return (res or [lead])[0]

    if not contacto_id:
        contacto_id = await contacto_para(org_id, user_id, nombre, telefono, email, fte, canal)

    if not asignado_a:
        asignado_a = await asignar_automatico(org_id, propiedad)

    fila = {
        "org_id": org_id, "user_id": user_id, "canal": canal, "estado": "sin_atender",
        "contacto_id": contacto_id, "propiedad_id": propiedad_id,
        "fuente_id": (fte or {}).get("id"), "fuente": (fte or {}).get("nombre") or fuente or CANALES.get(canal),
        "nombre": (nombre or "")[:120] or None, "telefono": (telefono or "")[:30] or None,
        "email": (email or "")[:160] or None, "mensaje": (mensaje or "")[:2000] or None,
        "referencia": referencia, "asignado_a": asignado_a, "asignado_en": ahora if asignado_a else None,
        "datos": datos or {}, "ultimo_mensaje_en": ahora, "created_at": ahora, "updated_at": ahora,
    }
    try:
        creados = await post_rows("buzon_leads", fila)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409 and referencia:    # carrera: otro webhook lo creó primero
            previo = await get_rows("buzon_leads", {"org_id": f"eq.{org_id}", "canal": f"eq.{canal}",
                                                    "referencia": f"eq.{referencia}", "select": "*", "limit": "1"})
            return previo[0] if previo else fila
        raise
    lead = creados[0] if creados else fila

    if contacto_id and asignado_a:
        try:   # el contacto queda con el mismo agente si aún no tenía
            await patch_rows("contactos", {"id": f"eq.{contacto_id}", "asignado_a": "is.null"}, {"asignado_a": asignado_a})
        except httpx.HTTPStatusError:
            pass
    if propiedad_id and contacto_id:
        try:   # liga el contacto como interesado en el inmueble de origen
            await post_rows("contactos_propiedades", {"contacto_id": contacto_id, "propiedad_id": propiedad_id,
                                                      "relacion": "interes", "user_id": user_id}, prefer="return=minimal")
        except httpx.HTTPStatusError:
            pass
    await avisar_asignacion(asignado_a, lead)
    return lead


async def registrar_desde_whatsapp(item: dict) -> None:
    """Hook del webhook de WhatsApp: cada mensaje entrante de un prospecto."""
    try:
        if item.get("es_asesor"):
            return
        numero = item.get("numero") or {}
        user_id = numero.get("user_id")
        if not user_id:
            return
        from routers.organizaciones import get_org_id_for_user
        org_id = await get_org_id_for_user(user_id)
        if not org_id:
            return
        wa = await get_rows("wa2_contactos", {"id": f"eq.{item.get('contacto_id')}",
                                              "select": "nombre,wa_id,contacto_crm_id", "limit": "1"})
        wa = wa[0] if wa else {}
        await registrar_lead(
            org_id=org_id, user_id=user_id, canal="whatsapp",
            nombre=wa.get("nombre") or "", telefono=wa.get("wa_id") or item.get("wa_id") or "",
            mensaje=item.get("texto") or "", fuente="WhatsApp",
            referencia=str(item.get("conversacion_id") or ""),
            contacto_id=wa.get("contacto_crm_id"),
            datos={"conversacion_id": item.get("conversacion_id"), "numero_id": numero.get("id")},
        )
    except Exception as e:
        log.warning("Buzón: no se registró el WhatsApp entrante: %s", e)
