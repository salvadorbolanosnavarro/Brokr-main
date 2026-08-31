"""Runtime evaluation of WhatsApp automation recipes."""
from __future__ import annotations


async def _correr_automatizaciones_core(item: dict, numero: dict, user_id: str, *, sb_get,
                                        datetime, timezone, _parse_ts, _AUTO_ULTIMA,
                                        _AUTO_COOLDOWN_SEG, _flujo_ejecutar, log,
                                        sb_patch, _now) -> bool:
    """Evalúa las recetas del usuario para este mensaje. Devuelve True si
    alguna receta respondió o pasó el chat al humano (la IA ya no contesta)."""
    autos = await sb_get("wa2_automatizaciones",
                         {"user_id": f"eq.{numero['user_id']}", "activa": "eq.true",
                          "or": f"(numero_id.is.null,numero_id.eq.{numero['id']})",
                          "select": "*", "limit": "100"})
    if not autos:
        return False

    texto = (item.get("texto") or "").lower()
    es_nuevo = None  # se calcula solo si alguna receta lo necesita
    silenciar_ia = False
    ahora = datetime.now(timezone.utc).timestamp()

    for auto in autos:
        disparador = auto.get("disparador")
        if disparador == "nuevo":
            if es_nuevo is None:
                entrantes = await sb_get("wa2_mensajes",
                                         {"conversacion_id": f"eq.{item['conversacion_id']}",
                                          "direction": "eq.in", "select": "id", "limit": "2"})
                es_nuevo = len(entrantes) <= 1
            if not es_nuevo:
                continue
        elif disparador == "nuevo_3m":
            # Cliente nuevo en el sentido amplio: nunca había escrito, o
            # llevaba más de 3 meses sin escribir (el snapshot se tomó antes
            # de guardar este mensaje, así que es la fecha correcta).
            prev_dt = _parse_ts(item.get("prev_inbound_at"))
            if prev_dt is not None and (datetime.now(timezone.utc) - prev_dt).days < 90:
                continue
        else:
            palabras = auto.get("palabras") or []
            if not any(p and str(p).lower() in texto for p in palabras):
                continue

        llave = f"{item['conversacion_id']}|{auto['id']}"
        if ahora - _AUTO_ULTIMA.get(llave, 0) < _AUTO_COOLDOWN_SEG:
            continue
        _AUTO_ULTIMA[llave] = ahora
        if len(_AUTO_ULTIMA) > 5000:
            for k in list(_AUTO_ULTIMA.keys())[:1000]:
                _AUTO_ULTIMA.pop(k, None)

        # Todos los pasos (viejos y nuevos) corren por el MISMO motor de
        # flujos: una sola implementación, un solo lugar donde equivocarse.
        try:
            if await _flujo_ejecutar(auto, item, numero, user_id):
                silenciar_ia = True
        except Exception as e:
            log.warning("Flujo %s falló: %s", auto.get("id"), e)

        try:
            await sb_patch("wa2_automatizaciones", {"id": f"eq.{auto['id']}"},
                           {"veces_usada": (auto.get("veces_usada") or 0) + 1, "updated_at": _now()})
        except Exception:
            pass

        if silenciar_ia:
            # Un flujo ya tomó la conversación (respondió o quedó esperando):
            # ningún otro flujo se le encima. Dos bots en un chat es el mismo
            # error que dos personas en un chat.
            break

    return silenciar_ia
