"""Motor del seguimiento automático.

Cada 5 minutos, por cada cuenta del piloto:
  1. Detecta quién contestó y detiene su secuencia (y te avisa: entra tú).
  2. Inscribe solos a los leads nuevos que se enfriaron (si la secuencia lo pide).
  3. Busca bajadas de precio y coincidencias nuevas (una vez por hora).
  4. Dentro del horario y del tope diario, manda los toques y avisos que tocan.
  5. Una vez al día, manda el resumen de prospectos calientes al celular.
Corre en UNA sola instancia: la misma bandera que los recordatorios
(RECORDATORIOS_ACTIVOS) lo apaga en staging y espejos.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from routers.seguimiento_calientes import calientes
from routers.seguimiento_datos import actualizar, ajustes_de, crear, en_lista, guardar, leer, log, usuarios_piloto
from routers.seguimiento_envio import (contacto_de, enviados_desde, enviar_plantilla, numero_de,
                                       proximo_permitido, zona_de)
from routers.seguimiento_eventos import detectar_eventos, enviar_eventos
from routers.seguimiento_schema import (MAX_INTENTOS, clasificar_error, en_horario, inicio_del_dia_utc,
                                        parse_ts, programar, render_variables, zona_valida)
from routers.whatsapp_crm_bridge import perfil_agente
from routers.whatsapp_messages import guardar_nota_sistema


_ULTIMA_DETECCION: dict[str, float] = {}


async def _push(user_id: str, titulo: str, cuerpo: str, datos: dict) -> None:
    try:
        from push import enviar_push
        await enviar_push(user_id, titulo, cuerpo, datos)
    except Exception as exc:
        log.info("seguimiento: push no enviado: %s", exc)


async def detectar_respuestas(user_id: str) -> int:
    activas = await leer("seg_inscripciones", {
        "user_id": f"eq.{user_id}", "estado": "eq.activa",
        "select": "id,secuencia_id,contacto_id,conversacion_id,inscrito_en,ultimo_envio_en", "limit": "1000"})
    if not activas:
        return 0
    convs = {c["contacto_id"]: c for c in await leer("wa2_conversaciones", {
        "contacto_id": en_lista({a["contacto_id"] for a in activas}),
        "select": "id,contacto_id,last_inbound_at"})}
    nombres = {s["id"]: s["nombre"] for s in await leer("seg_secuencias", {
        "user_id": f"eq.{user_id}", "select": "id,nombre"})}
    detenidas = 0
    for ins in activas:
        conv = convs.get(ins["contacto_id"]) or {}
        entrada = parse_ts(conv.get("last_inbound_at"))
        marca = parse_ts(ins.get("ultimo_envio_en")) or parse_ts(ins.get("inscrito_en"))
        if not entrada or not marca or entrada <= marca:
            continue
        hechas = await actualizar("seg_inscripciones", {"id": f"eq.{ins['id']}", "estado": "eq.activa"},
                                  {"estado": "respondio", "respondio_en": entrada.isoformat(), "proximo_en": None,
                                   "conversacion_id": conv.get("id")})
        if not hechas:
            continue
        detenidas += 1
        contacto = await contacto_de(ins["contacto_id"]) or {}
        nombre = (contacto.get("nombre") or contacto.get("wa_id") or "Tu prospecto").strip()
        secuencia = nombres.get(ins["secuencia_id"], "seguimiento")
        try:
            await guardar_nota_sistema(user_id, ins["contacto_id"], conv["id"],
                                       f"Contestó el seguimiento automático «{secuencia}». La secuencia se detuvo.")
        except Exception:
            pass
        await _push(user_id, "Contestó tu seguimiento", f"{nombre} te respondió. Entra tú: ya está caliente.",
                    {"tipo": "whatsapp", "conversation_id": conv.get("id")})
    return detenidas


async def auto_inscribir(user_id: str, ahora: datetime) -> int:
    secuencias = await leer("seg_secuencias", {"user_id": f"eq.{user_id}", "activa": "eq.true",
                                               "auto_leads_nuevos": "eq.true", "select": "*"})
    total = 0
    for sec in secuencias:
        pasos = sec.get("pasos") or []
        if not pasos:
            continue
        silencio = max(1, int(pasos[0].get("dias") or 1))
        desde = max(parse_ts(sec.get("created_at")) or ahora, ahora - timedelta(days=30))
        convs = await leer("wa2_conversaciones", {
            "user_id": f"eq.{user_id}", "numero_id": f"eq.{sec['numero_id']}",
            "created_at": f"gte.{desde.isoformat()}", "last_inbound_at": "not.is.null",
            "last_message_at": f"lte.{(ahora - timedelta(days=silencio)).isoformat()}",
            "select": "id,contacto_id", "limit": "100"})
        if not convs:
            continue
        ya = await leer("seg_inscripciones", {"contacto_id": en_lista({c["contacto_id"] for c in convs}),
                                              "select": "contacto_id,secuencia_id,estado"})
        ocupados = {i["contacto_id"] for i in ya if i["secuencia_id"] == sec["id"] or i["estado"] == "activa"}
        bajas = {c["id"] for c in await leer("wa2_contactos", {
            "id": en_lista({c["contacto_id"] for c in convs}), "opt_out": "eq.true", "select": "id"})}
        for c in convs:
            if c["contacto_id"] in ocupados or c["contacto_id"] in bajas:
                continue
            filas = await crear("seg_inscripciones", {
                "user_id": user_id, "secuencia_id": sec["id"], "numero_id": sec["numero_id"],
                "contacto_id": c["contacto_id"], "conversacion_id": c["id"], "estado": "activa",
                "paso": 0, "origen": "auto", "proximo_en": ahora.isoformat(), "inscrito_en": ahora.isoformat()})
            total += len(filas)
    return total


async def _cerrar(ins: dict, estado: str, motivo: str) -> None:
    await actualizar("seg_inscripciones", {"id": f"eq.{ins['id']}"},
                     {"estado": estado, "motivo": motivo[:200], "proximo_en": None})


async def correr_toques(user_id: str, zona: str, ahora: datetime, cupo: int) -> int:
    if cupo <= 0:
        return 0
    cola = await leer("seg_inscripciones", {
        "user_id": f"eq.{user_id}", "estado": "eq.activa", "proximo_en": f"lte.{ahora.isoformat()}",
        "select": "*", "order": "proximo_en.asc", "limit": str(min(200, cupo * 3))})
    if not cola:
        return 0
    secuencias = {s["id"]: s for s in await leer("seg_secuencias", {
        "id": en_lista({i["secuencia_id"] for i in cola}), "select": "*"})}
    agente = await perfil_agente(user_id)
    enviados = 0
    for ins in cola:
        if enviados >= cupo:
            break
        sec = secuencias.get(ins["secuencia_id"])
        if not sec or not sec.get("activa"):
            continue
        pasos = sec.get("pasos") or []
        idx = int(ins.get("paso") or 0)
        if idx >= len(pasos):
            await _cerrar(ins, "terminada", "Completó todos los toques.")
            continue
        contacto = await contacto_de(ins["contacto_id"])
        if not contacto:
            await _cerrar(ins, "error", "El contacto ya no existe.")
            continue
        if contacto.get("opt_out"):
            await _cerrar(ins, "baja", "Pidió no recibir mensajes.")
            continue
        espera = await proximo_permitido(contacto["id"], ahora)
        if espera:
            await actualizar("seg_inscripciones", {"id": f"eq.{ins['id']}"}, {"proximo_en": espera.isoformat()})
            continue
        # Reclamo atómico: si otra instancia ya lo tomó, aquí no se manda dos veces.
        tomado = await actualizar("seg_inscripciones", {"id": f"eq.{ins['id']}", "estado": "eq.activa",
                                                        "proximo_en": f"lte.{ahora.isoformat()}"},
                                  {"proximo_en": (ahora + timedelta(minutes=30)).isoformat()})
        if not tomado:
            continue
        numero = await numero_de(user_id, sec["numero_id"])
        if not numero:
            await _cerrar(ins, "error", "El número de WhatsApp ya no está conectado.")
            continue
        paso = pasos[idx]
        variables = render_variables(paso.get("variables") or [], {
            "nombre": contacto.get("nombre"), "agente": agente.get("nombre"), "zona": agente.get("zona")})
        conv, error = await enviar_plantilla(
            user_id, numero, contacto, paso["plantilla"], paso.get("idioma") or "es_MX", variables,
            etiqueta=f"Seguimiento · {sec['nombre']} · toque {idx + 1}", tipo="toque",
            inscripcion_id=ins["id"], paso=idx + 1)
        if not error:
            enviados += 1
            siguiente = idx + 1
            cambios = {"paso": siguiente, "intentos": 0, "ultimo_envio_en": ahora.isoformat(), "motivo": None,
                       "conversacion_id": (conv or {}).get("id") or ins.get("conversacion_id")}
            if siguiente >= len(pasos):
                cambios.update({"estado": "terminada", "proximo_en": None, "motivo": "Completó todos los toques."})
            else:
                cambios["proximo_en"] = programar(ahora, int(pasos[siguiente].get("dias") or 1),
                                                  int(sec.get("hora_envio") or 10), zona).isoformat()
            await actualizar("seg_inscripciones", {"id": f"eq.{ins['id']}"}, cambios)
            continue
        clase = clasificar_error(error)
        if clase == "token":
            await actualizar("seg_inscripciones", {"id": f"eq.{ins['id']}"},
                             {"proximo_en": (ahora + timedelta(hours=1)).isoformat()})
            log.warning("seguimiento: el número %s perdió su token; se pausa el ciclo", numero.get("id"))
            break
        if clase == "baja":
            await _cerrar(ins, "baja", "La persona dejó de aceptar mensajes de marketing.")
        elif clase == "plantilla":
            await _cerrar(ins, "error", f"Meta no aceptó la plantilla «{paso['plantilla']}»: revisa que esté aprobada.")
        elif clase == "invalido":
            await _cerrar(ins, "error", "Ese número no puede recibir mensajes de WhatsApp.")
        else:
            intentos = int(ins.get("intentos") or 0) + 1
            if intentos >= MAX_INTENTOS:
                await _cerrar(ins, "error", (error.get("message") or "Meta no pudo entregar el mensaje.")[:200])
            else:
                await actualizar("seg_inscripciones", {"id": f"eq.{ins['id']}"},
                                 {"intentos": intentos, "proximo_en": (ahora + timedelta(hours=2)).isoformat()})
    return enviados


async def resumen_diario(user_id: str, ajustes: dict, zona: str, ahora: datetime) -> bool:
    local = ahora.astimezone(zona_valida(zona))
    hoy = local.date().isoformat()
    if not ajustes.get("resumen_diario") or local.hour < 8 or local.weekday() == 6:
        return False
    if str(ajustes.get("ultimo_resumen") or "") == hoy:
        return False
    await guardar("seg_ajustes", {"user_id": user_id, "ultimo_resumen": hoy}, "user_id")
    lista = await calientes(user_id, 5)
    if not lista:
        return False
    primero = lista[0]
    razon = (primero["razones"] or ["Está activo"])[0].lower()
    await _push(user_id, f"Hoy: {len(lista)} prospecto{'s' if len(lista) != 1 else ''} caliente{'s' if len(lista) != 1 else ''}",
                f"Empieza por {primero['nombre'].title()}: {razon}.", {"tipo": "seguimiento", "url": "seguimiento.html"})
    return True


async def ciclo_usuario(user_id: str, *, forzar_eventos: bool = False) -> dict:
    ahora = datetime.now(timezone.utc)
    ajustes = await ajustes_de(user_id)
    zona = await zona_de(user_id)
    resultado = {"respuestas": await detectar_respuestas(user_id), "inscritos": await auto_inscribir(user_id, ahora),
                 "detectados": 0, "toques": 0, "avisos": 0, "en_horario": False}
    marca = _ULTIMA_DETECCION.get(user_id, 0)
    if forzar_eventos or ahora.timestamp() - marca >= 3600:
        _ULTIMA_DETECCION[user_id] = ahora.timestamp()
        resultado["detectados"] = await detectar_eventos(user_id, ahora)
    if en_horario(ahora, zona, int(ajustes["hora_inicio"]), int(ajustes["hora_fin"])):
        resultado["en_horario"] = True
        cupo = int(ajustes["tope_diario"]) - await enviados_desde(user_id, inicio_del_dia_utc(ahora, zona))
        resultado["toques"] = await correr_toques(user_id, zona, ahora, cupo)
        resultado["avisos"] = await enviar_eventos(user_id, ajustes, ahora, cupo - resultado["toques"])
    await resumen_diario(user_id, ajustes, zona, ahora)
    return resultado


async def ciclo() -> None:
    for user_id in sorted(usuarios_piloto()):
        try:
            await ciclo_usuario(user_id)
        except HTTPException as exc:
            log.warning("seguimiento: ciclo de %s detenido: %s", user_id, exc.detail)
        except Exception as exc:
            log.error("seguimiento: ciclo de %s falló: %s", user_id, exc)


async def bucle() -> None:
    await asyncio.sleep(45)
    while True:
        await ciclo()
        await asyncio.sleep(300)
