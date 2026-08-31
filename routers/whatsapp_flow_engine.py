from __future__ import annotations


async def _flujo_ejecutar_core(auto: dict, item: dict, numero: dict, user_id: str,
                               desde: int = 0, datos: dict | None = None, *,
                               WA_MAX_TEXTO, _wa_marcar_leido, _wa_send_text,
                               _guardar_mensaje, _FLUJO_MAX_PASOS_POR_TURNO,
                               sb_get, sb_patch, _now, log, enviar_push,
                               _flujo_estado_borrar, _flujo_nota_final,
                               _flujo_estado_guardar, _flujo_menu_texto) -> bool:
    """Ejecuta los pasos del flujo a partir de `desde`. Devuelve True si el
    flujo consumió la conversación (respondió algo o quedó esperando
    respuesta); False si la IA normal debe seguir con este mismo mensaje."""
    acciones = auto.get("acciones") or []
    datos = dict(datos or {})
    i = max(0, desde)
    respondio = False
    ejecutados = 0
    marcado_leido = False

    async def _enviar(texto: str) -> None:
        nonlocal respondio, marcado_leido
        if not marcado_leido:
            await _wa_marcar_leido(numero, item.get("wa_message_id"))
            marcado_leido = True
        wamid = await _wa_send_text(numero, item["wa_id"], texto[:WA_MAX_TEXTO])
        await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"],
                              wamid, "out", "ia", texto[:WA_MAX_TEXTO])
        respondio = True

    while i < len(acciones) and ejecutados < _FLUJO_MAX_PASOS_POR_TURNO:
        ejecutados += 1
        a = acciones[i] or {}
        tipo = a.get("tipo")
        valor = a.get("valor") or ""

        if tipo == "mensaje" and valor:
            await _enviar(valor)
            i += 1
        elif tipo == "etiqueta" and valor:
            try:
                rows = await sb_get("wa2_contactos", {"id": f"eq.{item['contacto_id']}",
                                                      "select": "etiquetas", "limit": "1"})
                tags = (rows[0].get("etiquetas") or []) if rows else []
                if valor not in tags:
                    await sb_patch("wa2_contactos", {"id": f"eq.{item['contacto_id']}"},
                                   {"etiquetas": (tags + [valor])[:20], "updated_at": _now()})
            except Exception as e:
                log.warning("Paso etiqueta del flujo falló: %s", e)
            i += 1
        elif tipo == "humano":
            await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                           {"ai_enabled": False, "ia_modo": "off"})
            await enviar_push(user_id, "Un flujo te pasó un chat",
                              f"El flujo '{auto.get('nombre')}' apagó la IA. Ya te toca a ti.",
                              datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})
            await _flujo_estado_borrar(item["conversacion_id"])
            await _flujo_nota_final(user_id, item["contacto_id"], auto.get("nombre") or "", datos)
            return True
        elif tipo == "ia":
            await sb_patch("wa2_conversaciones", {"id": f"eq.{item['conversacion_id']}"},
                           {"ia_modo": "on", "ai_enabled": True, "ia_pausada_hasta": None})
            await _flujo_estado_borrar(item["conversacion_id"])
            await _flujo_nota_final(user_id, item["contacto_id"], auto.get("nombre") or "", datos)
            return False
        elif tipo == "pregunta" and valor:
            await _enviar(valor)
            await _flujo_estado_guardar(user_id, item["conversacion_id"], auto["id"], i, datos)
            return True
        elif tipo == "opciones" and (a.get("opciones") or []):
            await _enviar(_flujo_menu_texto(a))
            datos["_intentos"] = 0
            await _flujo_estado_guardar(user_id, item["conversacion_id"], auto["id"], i, datos)
            return True
        else:
            i += 1

    await _flujo_estado_borrar(item["conversacion_id"])
    await _flujo_nota_final(user_id, item["contacto_id"], auto.get("nombre") or "", datos)
    return respondio
