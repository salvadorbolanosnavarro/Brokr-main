from __future__ import annotations


async def _revisar_token_core(numero: dict, err: dict | None, *, sb_patch, _now,
                               enviar_push, log) -> None:
    """Si Meta responde que el token ya no sirve, deja constancia y avisa.

    El token de un número puede morir sin que nadie haga nada malo: el agente
    revocó el permiso desde su Facebook, sacó a Broquer de su Business, o Meta
    lo caducó. Cuando eso pasa NO hay forma de renovarlo solos — el token de
    integración de negocio se emite una sola vez, en el Embedded Signup. El
    único arreglo real es que el agente vuelva a apretar 'Conectar número'.

    Así que lo que se puede hacer, y es lo que hace esto, es enterarse a la
    primera y decírselo, en vez de dejar que los mensajes se pierdan en
    silencio durante días. También apaga la IA de ese número: no tiene caso
    quemar llamadas a Claude generando respuestas que nunca van a salir.
    """
    if not err or err.get("code") not in (190, 102):
        return
    numero_id = numero.get("id")
    if not numero_id:
        return
    try:
        if numero.get("token_valido") is False:
            return  # ya estaba marcado, no repitas el aviso en cada mensaje
        await sb_patch("wa2_numeros", {"id": f"eq.{numero_id}"},
                      {"token_valido": False, "token_error_at": _now(), "ia_enabled": False})
        numero["token_valido"] = False
        await enviar_push(numero.get("user_id"), "Tu WhatsApp se desconectó",
                          "Meta dejó de aceptar la conexión de tu número. Entra a WhatsApp en "
                          "Broquer y vuelve a apretar 'Conectar número' para reactivarlo.",
                          datos={"tipo": "whatsapp"})
        log.error("Token inválido para el número %s (user %s): %s",
                  numero.get("phone_number_id"), numero.get("user_id"), err.get("message"))
    except Exception as e:  # pragma: no cover — avisar nunca debe tumbar el envío
        log.warning("No se pudo marcar el token inválido de %s: %s", numero_id, e)
