"""Un solo camino para mandar un mensaje automático del seguimiento.

Toques de secuencia y avisos por evento pasan por aquí: se manda la
plantilla aprobada con la Cloud API, se deja en la bandeja de WhatsApp (para
que el agente vea exactamente qué recibió el prospecto) y se anota en la
bitácora seg_envios con el resultado de Meta.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.config import settings
from routers.seguimiento_datos import crear, leer, log
from routers.seguimiento_schema import SEPARACION_HORAS, parse_ts
from routers.whatsapp_cloud_api import send_template
from routers.whatsapp_contacts import get_o_crea_conversacion
from routers.whatsapp_data import sb_get
from routers.whatsapp_messages import guardar_mensaje


_NUMEROS: dict[str, tuple[float, dict]] = {}


async def numero_de(user_id: str, numero_id: str) -> dict | None:
    """Número con su token ya descifrado; se reusa 10 min dentro del ciclo."""
    ahora = datetime.now(timezone.utc).timestamp()
    guardado = _NUMEROS.get(numero_id)
    if guardado and ahora - guardado[0] < 600:
        return guardado[1]
    filas = await sb_get("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": f"eq.{user_id}",
                                         "select": "*", "limit": "1"})
    numero = filas[0] if filas else None
    if numero:
        _NUMEROS[numero_id] = (ahora, numero)
    return numero


async def zona_de(user_id: str) -> str:
    try:
        filas = await leer("wa2_entrenamiento", {"user_id": f"eq.{user_id}", "select": "zona_horaria", "limit": "1"})
    except Exception:
        filas = []
    return (filas[0].get("zona_horaria") if filas else None) or settings.wa2_zone_default


async def contacto_de(contacto_id: str) -> dict | None:
    filas = await leer("wa2_contactos", {"id": f"eq.{contacto_id}",
                                         "select": "id,user_id,numero_id,wa_id,nombre,opt_out,contacto_crm_id",
                                         "limit": "1"})
    return filas[0] if filas else None


async def proximo_permitido(contacto_id: str, ahora: datetime) -> datetime | None:
    """Si el contacto recibió un mensaje automático hace menos de 44 h,
    devuelve cuándo se le puede volver a escribir; si no, None."""
    filas = await leer("seg_envios", {"contacto_id": f"eq.{contacto_id}", "estado": "eq.enviado",
                                      "select": "created_at", "order": "created_at.desc", "limit": "1"})
    ultimo = parse_ts(filas[0].get("created_at")) if filas else None
    if ultimo and ahora - ultimo < timedelta(hours=SEPARACION_HORAS):
        return ultimo + timedelta(hours=SEPARACION_HORAS)
    return None


async def enviados_desde(user_id: str, desde: datetime) -> int:
    filas = await leer("seg_envios", {"user_id": f"eq.{user_id}", "estado": "eq.enviado",
                                      "created_at": f"gte.{desde.isoformat()}", "select": "id", "limit": "500"})
    return len(filas)


async def enviar_plantilla(user_id: str, numero: dict, contacto: dict, plantilla: str, idioma: str,
                           variables: list[str], *, etiqueta: str, tipo: str,
                           inscripcion_id: str | None = None, evento_id: str | None = None,
                           paso: int | None = None) -> tuple[dict | None, dict | None]:
    """Devuelve (conversación, error). error=None significa que Meta lo aceptó."""
    wamid, error = await send_template(numero, contacto.get("wa_id"), plantilla, idioma, variables)
    bitacora = {"user_id": user_id, "contacto_id": contacto["id"], "inscripcion_id": inscripcion_id,
                "evento_id": evento_id, "tipo": tipo, "paso": paso, "plantilla": plantilla,
                "estado": "fallido" if error else "enviado", "wamid": wamid,
                "error": ((error or {}).get("message") or "")[:300] or None}
    try:
        await crear("seg_envios", bitacora)
    except Exception as exc:  # la bitácora nunca debe tumbar un envío ya hecho
        log.warning("seguimiento: no se anotó el envío de %s: %s", contacto["id"], exc)
    if error:
        return None, error
    conv = await get_o_crea_conversacion(user_id, numero["id"], contacto["id"], ia_default=False)
    if conv.get("id"):
        resumen = f"[{etiqueta} · plantilla {plantilla}]" + (" " + " · ".join(variables) if variables else "")
        await guardar_mensaje(user_id, contacto["id"], conv["id"], wamid, "out", "agente", resumen)
    return conv, None
