from __future__ import annotations


async def _correr_campana_core(campana_id: str, numero: dict, audiencia: list,
                               plantilla: str, idioma: str, variables: list, *,
                               httpx, GRAPH_API, _variables_para, sb_post, _now,
                               _get_o_crea_conversacion, _guardar_mensaje, log,
                               sb_patch, asyncio, enviar_push):
    enviados = fallidos = 0
    async with httpx.AsyncClient(timeout=20) as c:
        for i, ct in enumerate(audiencia):
            vars_ct = _variables_para(ct, variables)
            componentes = []
            if vars_ct:
                componentes.append({"type": "body",
                                    "parameters": [{"type": "text", "text": v} for v in vars_ct]})
            wamid, err = None, ""
            try:
                r = await c.post(f"{GRAPH_API}/{numero['phone_number_id']}/messages",
                                 headers={"Authorization": f"Bearer {numero['access_token']}"},
                                 json={"messaging_product": "whatsapp", "to": ct["wa_id"],
                                       "type": "template",
                                       "template": {"name": plantilla,
                                                    "language": {"code": idioma},
                                                    "components": componentes}})
                if r.status_code < 400:
                    msgs = r.json().get("messages") or []
                    wamid = msgs[0].get("id") if msgs else None
                else:
                    try:
                        err = (r.json().get("error", {}).get("message") or "")[:200]
                    except Exception:
                        err = r.text[:200]
                    if not err:
                        err = f"Meta respondió {r.status_code}"
            except Exception as e:
                err = str(e)[:200]

            ok = not err
            try:
                await sb_post("wa2_campana_envios",
                              {"campana_id": campana_id, "user_id": numero["user_id"],
                               "contacto_id": ct["id"], "wa_id": ct.get("wa_id"),
                               "nombre": ct.get("nombre"),
                               "estado": "enviado" if ok else "fallido",
                               "error": err or None, "created_at": _now()})
            except Exception:
                pass

            if ok:
                enviados += 1
                # Reflejar el envío en la bandeja, en la conversación de esa
                # persona (si no tenía, se crea con la IA apagada: fue un
                # masivo, no una conversación que la IA deba retomar sola).
                try:
                    conv = await _get_o_crea_conversacion(numero["user_id"], numero["id"],
                                                          ct["id"], ia_default=False)
                    resumen = f"[Campaña · plantilla {plantilla}]"
                    await _guardar_mensaje(numero["user_id"], ct["id"], conv["id"],
                                          wamid, "out", "agente", resumen)
                except Exception:
                    pass
            else:
                fallidos += 1
                log.warning("Campaña %s: fallo con %s: %s", campana_id, ct.get("wa_id"), err)

            if (i + 1) % 10 == 0:
                try:
                    await sb_patch("wa2_campanas", {"id": f"eq.{campana_id}"},
                                   {"enviados": enviados, "fallidos": fallidos})
                except Exception:
                    pass
            # Pausa corta entre envíos: no saturar el API de Meta ni parecer spam.
            await asyncio.sleep(0.5)

    try:
        await sb_patch("wa2_campanas", {"id": f"eq.{campana_id}"},
                       {"enviados": enviados, "fallidos": fallidos,
                        "estado": "terminada", "terminado_at": _now()})
    except Exception:
        pass
    await enviar_push(numero.get("user_id"), "Campaña terminada",
                      f"Se enviaron {enviados} mensajes"
                      + (f" ({fallidos} fallaron)" if fallidos else "") + ".",
                      datos={"tipo": "whatsapp"})
