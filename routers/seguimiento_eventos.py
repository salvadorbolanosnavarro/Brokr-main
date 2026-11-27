"""Avisos por evento: el seguimiento que nadie siente como spam.

Dos eventos le dan al prospecto una razón real para recibir un mensaje:
  · precio       un inmueble que ya le mandaste bajó de precio.
  · coincidencia salió un inmueble que coincide con su requerimiento
                 (las alertas de búsqueda ya lo detectan; aquí se le avisa).
Se detectan una vez por hora y se mandan con las plantillas que el agente
eligió en Ajustes, dentro del horario, del tope diario y sin escribirle a
nadie dos veces en menos de 44 h.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from routers.alertas import liga_publica
from routers.seguimiento_datos import actualizar, crear, en_lista, guardar, leer, log
from routers.seguimiento_envio import contacto_de, enviar_plantilla, numero_de, proximo_permitido
from routers.seguimiento_schema import primer_nombre


def precio_de(p: dict) -> float | None:
    for valor in [p.get("precio")] + [o.get("precio") or o.get("amount") for o in (p.get("operaciones") or [])
                                      if isinstance(o, dict)]:
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            continue
        if numero > 0:
            return numero
    return None


def precio_texto(valor: float | None, moneda: str | None) -> str:
    return f"${valor:,.0f} {moneda or 'MXN'}" if valor else "precio a consultar"


def titulo_de(p: dict) -> str:
    base = (p.get("titulo") or p.get("tipo") or "Inmueble").strip()
    zona = ", ".join(x for x in (p.get("colonia"), p.get("ciudad")) if x)
    return f"{base} en {zona}" if zona and zona.lower() not in base.lower() else base


async def _interesados(user_id: str, propiedad_id: str) -> dict[str, str]:
    """Contactos de WhatsApp (id → número) a quienes ya se les mandó el inmueble."""
    salida: dict[str, str] = {}
    for c in await leer("wa2_conversaciones", {
            "user_id": f"eq.{user_id}", "ultimas_propiedades": f"cs.{json.dumps([{'id': propiedad_id}])}",
            "select": "contacto_id,numero_id", "limit": "200"}):
        salida[c["contacto_id"]] = c["numero_id"]
    crm = [a["contacto_id"] for a in await leer("alertas_enviadas", {
        "propiedad_id": f"eq.{propiedad_id}", "estado": "eq.enviada", "select": "contacto_id", "limit": "200"})]
    if crm:
        for c in await leer("wa2_contactos", {"user_id": f"eq.{user_id}", "contacto_crm_id": en_lista(crm),
                                              "select": "id,numero_id"}):
            salida.setdefault(c["id"], c["numero_id"])
    return salida


async def _registrar(user_id: str, contacto_id: str, numero_id: str, tipo: str, propiedad_id: str,
                     clave: str, detalle: dict) -> int:
    filas = await crear("seg_eventos", {"user_id": user_id, "contacto_id": contacto_id, "numero_id": numero_id,
                                        "tipo": tipo, "propiedad_id": propiedad_id, "clave": clave,
                                        "detalle": detalle, "estado": "pendiente"})
    return len(filas)


async def detectar_bajadas(user_id: str) -> int:
    props = await leer("propiedades", {"user_id": f"eq.{user_id}", "estatus": "eq.activa",
                                       "select": "id,titulo,tipo,colonia,ciudad,precio,moneda,operaciones",
                                       "limit": "2000"})
    if not props:
        return 0
    previos: dict[str, float] = {}
    ids = [p["id"] for p in props]
    for i in range(0, len(ids), 150):
        for f in await leer("seg_precios", {"propiedad_id": en_lista(ids[i:i + 150]), "select": "propiedad_id,precio"}):
            previos[f["propiedad_id"]] = float(f["precio"])
    ahora = datetime.now(timezone.utc).isoformat()
    cambios, nuevos = [], 0
    for p in props:
        precio = precio_de(p)
        if precio is None or previos.get(p["id"]) == precio:
            continue
        antes = previos.get(p["id"])
        cambios.append({"propiedad_id": p["id"], "user_id": user_id, "precio": precio,
                        "moneda": p.get("moneda") or "MXN", "visto_en": ahora})
        if antes is None or precio >= antes * 0.995:
            continue
        detalle = {"titulo": titulo_de(p), "antes": antes, "ahora": precio, "moneda": p.get("moneda") or "MXN"}
        for contacto_id, numero_id in (await _interesados(user_id, p["id"])).items():
            nuevos += await _registrar(user_id, contacto_id, numero_id, "precio", p["id"], f"{precio:.0f}", detalle)
    if cambios:
        await guardar("seg_precios", cambios, "propiedad_id")
    return nuevos


async def detectar_coincidencias(user_id: str, ahora: datetime) -> int:
    reqs = {r["id"]: r for r in await leer("requerimientos_busqueda", {
        "user_id": f"eq.{user_id}", "activo": "eq.true", "select": "id,contacto_id", "limit": "500"})}
    if not reqs:
        return 0
    pendientes = await leer("alertas_enviadas", {
        "requerimiento_id": en_lista(reqs), "estado": "eq.pendiente",
        "detectada_en": f"gte.{(ahora - timedelta(days=3)).isoformat()}",
        "select": "requerimiento_id,contacto_id,propiedad_id", "limit": "300"})
    if not pendientes:
        return 0
    wa = {c["contacto_crm_id"]: c for c in await leer("wa2_contactos", {
        "user_id": f"eq.{user_id}", "contacto_crm_id": en_lista({a["contacto_id"] for a in pendientes}),
        "select": "id,numero_id,contacto_crm_id"})}
    props = {p["id"]: p for p in await leer("propiedades", {
        "id": en_lista({a["propiedad_id"] for a in pendientes}),
        "select": "id,titulo,tipo,colonia,ciudad,precio,moneda,operaciones"})}
    nuevos = 0
    for a in pendientes:
        contacto, p = wa.get(a["contacto_id"]), props.get(a["propiedad_id"])
        if not contacto or not p:
            continue
        detalle = {"titulo": titulo_de(p), "ahora": precio_de(p), "moneda": p.get("moneda") or "MXN",
                   "requerimiento_id": a["requerimiento_id"], "contacto_crm_id": a["contacto_id"]}
        nuevos += await _registrar(user_id, contacto["id"], contacto["numero_id"], "coincidencia",
                                   p["id"], "nueva", detalle)
    return nuevos


async def detectar_eventos(user_id: str, ahora: datetime) -> int:
    total = 0
    for paso in (detectar_bajadas(user_id), detectar_coincidencias(user_id, ahora)):
        try:
            total += await paso
        except Exception as exc:
            log.warning("seguimiento: detección de eventos de %s falló: %s", user_id, exc)
    return total


async def _marcar_alerta_enviada(user_id: str, ev: dict) -> None:
    det = ev.get("detalle") or {}
    if not det.get("requerimiento_id"):
        return
    ahora = datetime.now(timezone.utc).isoformat()
    try:
        await actualizar("alertas_enviadas", {"requerimiento_id": f"eq.{det['requerimiento_id']}",
                                              "propiedad_id": f"eq.{ev['propiedad_id']}"},
                         {"estado": "enviada", "canal": "whatsapp", "enviada_en": ahora, "enviada_por": user_id})
        await crear("actividades", {"user_id": user_id, "contacto_id": det.get("contacto_crm_id"), "tipo": "nota",
                                    "texto": f"Seguimiento automático: se le avisó por WhatsApp de {det.get('titulo')}."})
    except Exception as exc:
        log.info("seguimiento: no se pudo reflejar la alerta enviada: %s", exc)


async def enviar_eventos(user_id: str, ajustes: dict, ahora: datetime, cupo: int) -> int:
    if not ajustes.get("eventos_activos") or cupo <= 0:
        return 0
    vencidos = (ahora - timedelta(days=5)).isoformat()
    await actualizar("seg_eventos", {"user_id": f"eq.{user_id}", "estado": "eq.pendiente",
                                     "created_at": f"lt.{vencidos}"},
                     {"estado": "omitido", "motivo": "Pasaron 5 días sin poder avisarle."})
    pendientes = await leer("seg_eventos", {"user_id": f"eq.{user_id}", "estado": "eq.pendiente",
                                            "select": "*", "order": "created_at.asc", "limit": str(min(100, cupo * 3))})
    enviados = 0
    for ev in pendientes:
        if enviados >= cupo:
            break
        plantilla = ajustes.get("plantilla_precio") if ev["tipo"] == "precio" else ajustes.get("plantilla_coincidencia")
        if not plantilla:
            continue
        contacto = await contacto_de(ev["contacto_id"])
        if not contacto or contacto.get("opt_out"):
            await actualizar("seg_eventos", {"id": f"eq.{ev['id']}"}, {"estado": "omitido", "motivo": "Pidió no recibir mensajes."})
            continue
        if await proximo_permitido(contacto["id"], ahora):
            continue
        tomado = await actualizar("seg_eventos", {"id": f"eq.{ev['id']}", "estado": "eq.pendiente"}, {"estado": "enviando"})
        numero = await numero_de(user_id, ev["numero_id"]) if tomado else None
        if not numero:
            if tomado:
                await actualizar("seg_eventos", {"id": f"eq.{ev['id']}"}, {"estado": "fallido", "motivo": "Número desconectado."})
            continue
        det = ev.get("detalle") or {}
        variables = [primer_nombre(contacto.get("nombre")), det.get("titulo") or "el inmueble",
                     precio_texto(det.get("ahora"), det.get("moneda")), liga_publica(ev["propiedad_id"], user_id)]
        etiqueta = "Aviso · bajó de precio" if ev["tipo"] == "precio" else "Aviso · nueva opción"
        _, error = await enviar_plantilla(user_id, numero, contacto, plantilla, ajustes.get("idioma") or "es_MX",
                                          variables, etiqueta=etiqueta, tipo=ev["tipo"], evento_id=ev["id"])
        if error:
            await actualizar("seg_eventos", {"id": f"eq.{ev['id']}"},
                             {"estado": "fallido", "motivo": (error.get("message") or "Meta no lo entregó.")[:200]})
            continue
        enviados += 1
        await actualizar("seg_eventos", {"id": f"eq.{ev['id']}"}, {"estado": "enviado", "enviado_en": ahora.isoformat()})
        if ev["tipo"] == "coincidencia":
            await _marcar_alerta_enviada(user_id, ev)
    return enviados
