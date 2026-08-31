from __future__ import annotations


async def _flujo_continuar_core(estado: dict, item: dict, numero: dict, user_id: str, *,
                                _parse_ts, datetime, timezone, _FLUJO_CADUCA_HORAS,
                                _flujo_estado_borrar, sb_get, _flujo_ejecutar,
                                _FLUJO_MAX_REINTENTOS, _flujo_estado_guardar,
                                _wa_send_text, _flujo_menu_texto, _guardar_mensaje) -> bool:
    """Un flujo estaba esperando respuesta y llegó un mensaje del prospecto.
    Devuelve True si el flujo lo consumió; False si debe seguir el camino
    normal (automatizaciones nuevas / IA)."""
    ult = _parse_ts(estado.get("updated_at"))
    if ult and (datetime.now(timezone.utc) - ult).total_seconds() > _FLUJO_CADUCA_HORAS * 3600:
        await _flujo_estado_borrar(item["conversacion_id"])
        return False
    try:
        autos = await sb_get("wa2_automatizaciones", {"id": f"eq.{estado['automatizacion_id']}",
                                                      "select": "*", "limit": "1"})
    except Exception:
        autos = []
    if not autos or not autos[0].get("activa", True):
        await _flujo_estado_borrar(item["conversacion_id"])
        return False
    auto = autos[0]
    acciones = auto.get("acciones") or []
    paso_idx = int(estado.get("paso") or 0)
    datos = dict(estado.get("datos") or {})
    if paso_idx >= len(acciones):
        await _flujo_estado_borrar(item["conversacion_id"])
        return False
    paso = acciones[paso_idx] or {}
    texto = (item.get("texto") or "").strip()

    if paso.get("tipo") == "pregunta":
        campo = paso.get("guardar") or "nota"
        datos[campo] = texto[:300]
        return await _flujo_ejecutar(auto, item, numero, user_id,
                                     desde=paso_idx + 1, datos=datos)

    if paso.get("tipo") == "opciones":
        ops = paso.get("opciones") or []
        elegido = None
        limpio = texto.lower().strip(".!¡¿? ")
        if limpio.isdigit() and 1 <= int(limpio) <= len(ops):
            elegido = ops[int(limpio) - 1]
        else:
            for op in ops:
                t = (op.get("texto") or "").lower()
                if t and (t in limpio or limpio in t):
                    elegido = op
                    break
        if elegido is None:
            intentos = int(datos.get("_intentos") or 0) + 1
            if intentos > _FLUJO_MAX_REINTENTOS:
                await _flujo_estado_borrar(item["conversacion_id"])
                return False
            datos["_intentos"] = intentos
            await _flujo_estado_guardar(user_id, item["conversacion_id"], auto["id"], paso_idx, datos)
            wamid = await _wa_send_text(numero, item["wa_id"],
                                        "Perdón, no te entendí. Respóndeme con el número de una opción:\n"
                                        + _flujo_menu_texto(paso))
            await _guardar_mensaje(user_id, item["contacto_id"], item["conversacion_id"],
                                  wamid, "out", "ia",
                                  "Perdón, no te entendí. Respóndeme con el número de una opción:\n"
                                  + _flujo_menu_texto(paso))
            return True
        datos.pop("_intentos", None)
        datos.setdefault("nota", "")
        eleccion = elegido.get("texto") or ""
        datos["nota"] = (datos["nota"] + (" · " if datos["nota"] else "") + f"Eligió: {eleccion}")[:400]
        try:
            ir = int(elegido.get("ir") or 0)
        except Exception:
            ir = 0
        destino = (ir - 1) if ir >= 1 else (paso_idx + 1)
        if destino >= len(acciones):
            destino = len(acciones)
        return await _flujo_ejecutar(auto, item, numero, user_id, desde=destino, datos=datos)

    await _flujo_estado_borrar(item["conversacion_id"])
    return False
