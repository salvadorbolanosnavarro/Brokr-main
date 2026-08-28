"""WhatsApp message persistence and property-resolution helpers."""
from __future__ import annotations


async def _guardar_mensaje_core(user_id: str, contacto_id: str, conversacion_id: str, wamid: str | None,
                                direction: str, sender: str, body: str, media_url: str | None = None,
                                media_path: str | None = None, *, _now, sb_post, sb_get, log, sb_patch) -> None:
    fila = {"user_id": user_id, "contacto_id": contacto_id, "conversacion_id": conversacion_id,
            "direction": direction, "sender": sender, "body": body, "media_url": media_url,
            "media_path": media_path, "created_at": _now()}
    if wamid:
        fila["wa_message_id"] = wamid
    guardado = await sb_post("wa2_mensajes", fila)
    if not guardado and wamid:
        ya = await sb_get("wa2_mensajes", {"wa_message_id": f"eq.{wamid}", "select": "id", "limit": "1"})
        if not ya:
            log.error("wa2_mensajes NO guardado: conv=%s sender=%s", conversacion_id, sender)
    cambios_conv = {"last_message_at": _now()}
    if direction == "in":
        # Esto (no 'last_message_at') es lo que de verdad marca la ventana de
        # 24h de WhatsApp: se cuenta desde el último mensaje del PROSPECTO,
        # no desde el último mensaje de quien sea (agente, IA, prospecto).
        cambios_conv["last_inbound_at"] = _now()
        # Se guarda el id de Meta del último mensaje del prospecto: es lo que
        # se necesita para mandarle la palomita azul cuando el agente abra la
        # conversación en Broquer (no antes).
        if wamid:
            cambios_conv["last_inbound_wamid"] = wamid
    await sb_patch("wa2_conversaciones", {"id": f"eq.{conversacion_id}"}, cambios_conv)


def _resolver_inmueble_id_core(inmueble_txt: str, ultimas: list) -> str | None:
    """Si el prospecto ya vio 1 sola propiedad en esta charla, es esa. Si vio
    varias, se intenta encontrar cuál por el texto que puso la IA en 'inmueble'."""
    if not ultimas:
        return None
    if len(ultimas) == 1:
        return ultimas[0].get("id")
    texto = (inmueble_txt or "").strip().lower()
    if not texto:
        return None
    for p in ultimas:
        titulo = (p.get("titulo") or "").strip().lower()
        if titulo and (titulo in texto or texto in titulo):
            return p.get("id")
    return None
