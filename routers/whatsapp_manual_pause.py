from __future__ import annotations


async def _pausar_por_respuesta_manual_core(conv: dict, numero: dict, entren: dict | None = None, *,
                                             _entrenamiento_de, _modo_conv, datetime,
                                             timezone, timedelta, sb_patch,
                                             _guardar_nota_sistema=None) -> dict:
    """El agente respondió a mano (desde Broquer o desde el WhatsApp de su
    celular). Según la configuración del número, la IA se hace a un lado en
    ese chat: para siempre, o por un rato (pausa temporal). En cualquier caso
    se cierra la sesión de "cliente nuevo": el agente ya tomó el chat."""
    if entren is None:
        entren = await _entrenamiento_de(numero["user_id"], numero["id"])
    info = {"ia_pausada": False, "ia_pausada_hasta": None, "para_siempre": False}
    cambios: dict = {"ia_sesion_nueva": False}
    if entren.get("pausa_al_responder", True) and _modo_conv(conv) != "off":
        dur = 0
        try:
            dur = int(entren.get("pausa_duracion_min") or 0)
        except Exception:
            pass
        if dur <= 0:
            cambios.update({"ia_modo": "off", "ai_enabled": False, "ia_pausada_hasta": None})
            info.update({"ia_pausada": True, "para_siempre": True})
        else:
            hasta = (datetime.now(timezone.utc) + timedelta(minutes=dur)).isoformat()
            cambios["ia_pausada_hasta"] = hasta
            info.update({"ia_pausada": True, "ia_pausada_hasta": hasta})
    guardado = await sb_patch("wa2_conversaciones", {"id": f"eq.{conv['id']}"}, cambios)
    if not guardado and info["ia_pausada"]:
        # Migración pendiente (columnas nuevas ausentes): degradar al
        # comportamiento clásico para que JAMÁS contesten dos en un chat.
        await sb_patch("wa2_conversaciones", {"id": f"eq.{conv['id']}"}, {"ai_enabled": False})
    conv.update({k: v for k, v in cambios.items()})
    # Nota visible en el hilo: sin esto, la única señal de que la IA se hizo
    # a un lado era un push que el asesor podía no ver — y el chat se veía
    # "apagado solo" sin explicación.
    if info["ia_pausada"] and _guardar_nota_sistema is not None:
        texto = ("⏸️ La IA quedó en pausa en este chat: alguien contestó a mano "
                 "(desde Broquer o desde el celular conectado). Enciéndela de nuevo "
                 "desde el control de IA de la conversación cuando quieras.") \
            if info["para_siempre"] else \
            ("⏸️ La IA hace una pausa temporal en este chat porque alguien contestó a "
             "mano: vuelve sola en unos minutos, o enciéndela ya desde el control de IA.")
        await _guardar_nota_sistema(numero["user_id"], conv.get("contacto_id"), conv["id"], texto)
    return info
