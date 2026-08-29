from __future__ import annotations


async def _procesar_en_segundo_plano_core(item: dict, *, sb_get, enviar_push,
                                           _flujo_estado_de, _flujo_continuar,
                                           log, _correr_automatizaciones,
                                           WA2_DEBOUNCE, asyncio, _lock_conv,
                                           _broq_asesor, _responder_conversacion):
    numero = item["numero"]
    user_id = numero["user_id"]

    # OJO: aquí YA NO se manda la palomita azul. Antes se mandaba en cuanto
    # entraba el mensaje, aunque la IA estuviera apagada o el chat lo tuviera
    # que atender el agente: el prospecto veía "leído" sin que nadie lo hubiera
    # leído, y del lado de Broquer todo aparecía como atendido. Ahora la
    # palomita se manda solo cuando la IA de verdad va a contestar (más abajo,
    # en _responder_conversacion) o cuando el agente abre el chat en Broquer.

    # El aviso al celular del agente va ANTES de agrupar: aunque esta tarea se
    # retire por ráfaga, el agente tiene que enterarse de TODOS los mensajes.
    if not item.get("es_asesor"):  # avisarle al asesor de su propio mensaje no tiene caso
        contacto_push = await sb_get("wa2_contactos", {"id": f"eq.{item['contacto_id']}",
                                                       "select": "nombre", "limit": "1"})
        await enviar_push(user_id,
                          (contacto_push[0].get("nombre") if contacto_push else None) or "Nuevo mensaje de WhatsApp",
                          item["texto"], datos={"tipo": "whatsapp", "conversation_id": item["conversacion_id"]})

    # ── FLUJO EN CURSO ───────────────────────────────────────────────────
    # Si esta conversación tiene un flujo esperando respuesta (una pregunta
    # o un menú de opciones), este mensaje ES esa respuesta: la consume el
    # flujo, no la IA. Es la garantía de que un flujo jamás se corta a medias.
    if not item.get("es_asesor"):
        try:
            estado = await _flujo_estado_de(item["conversacion_id"])
            if estado and await _flujo_continuar(estado, item, numero, user_id):
                return
        except Exception as e:
            log.warning("Flujo activo falló (se sigue normal): %s", e)

    # ── FLUJOS / AUTOMATIZACIONES (recetas) ──────────────────────────────
    # Corren ANTES de agrupar ráfagas y antes de la IA: si el mensaje dispara
    # un flujo que responde, pregunta o pasa el chat (a ti o a la IA), ese
    # flujo manda y la IA ya no dice nada encima. Si el flujo solo pone
    # etiquetas, el camino normal (IA incluida) sigue igual.
    if not item.get("es_asesor"):
        try:
            if await _correr_automatizaciones(item, numero, user_id):
                return
        except Exception as e:
            log.warning("Automatizaciones fallaron (se sigue normal): %s", e)

    # ── AGRUPAR RÁFAGAS ──────────────────────────────────────────────────
    # La gente escribe en WhatsApp a pedacitos. Se espera unos segundos y, si
    # mientras tanto entró otro mensaje del prospecto, ESTA tarea se retira:
    # la que atienda el último mensaje contestará una sola vez y ya con todo
    # el contexto. Sin esto salían tres respuestas encimadas, se contradecían
    # entre sí y se pagaban tres llamadas a la IA por una sola pregunta.
    if WA2_DEBOUNCE:
        await asyncio.sleep(WA2_DEBOUNCE)
        ultimos = await sb_get("wa2_mensajes", {
            "conversacion_id": f"eq.{item['conversacion_id']}", "direction": "eq.in",
            "select": "wa_message_id", "order": "created_at.desc", "limit": "1"})
        if ultimos and item.get("wa_message_id") and \
           ultimos[0].get("wa_message_id") != item["wa_message_id"]:
            log.info("Ráfaga: se descarta la respuesta al mensaje %s, ya llegó uno más nuevo",
                     item["wa_message_id"])
            return

    async with _lock_conv(item["conversacion_id"]):
        if item.get("es_asesor"):
            await _broq_asesor(item, numero, user_id)
        else:
            await _responder_conversacion(item, numero, user_id)
