"""Prospectos calientes: a quién conviene atender hoy y por qué.

La calificación es transparente (cada punto tiene una razón que se muestra
al agente) y sale solo de lo que ya pasó en WhatsApp: qué tan reciente y
qué tan seguido escribe, si contestó un seguimiento, si está esperando
respuesta y si usó palabras de intención de compra o visita.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from routers.seguimiento_datos import en_lista, leer
from routers.seguimiento_schema import parse_ts, primer_nombre


INTENCION = {
    "visita": "Pidió visita", "visitar": "Pidió visita", "verla": "Pidió visita", "verlo": "Pidió visita",
    "cita": "Pidió visita", "conocerla": "Pidió visita", "puedo ir": "Pidió visita",
    "crédito": "Habló de crédito", "credito": "Habló de crédito", "infonavit": "Habló de crédito",
    "fovissste": "Habló de crédito", "hipoteca": "Habló de crédito", "precalific": "Habló de crédito",
    "contado": "Paga de contado", "apartar": "Quiere apartar", "apartado": "Quiere apartar",
    "enganche": "Habló de enganche", "oferta": "Quiere ofertar", "negociable": "Quiere negociar",
    "disponible": "Preguntó disponibilidad", "sigue en venta": "Preguntó disponibilidad",
}


def _hace(dt: datetime, ahora: datetime) -> str:
    seg = max(0, int((ahora - dt).total_seconds()))
    if seg < 3600:
        return f"hace {max(1, seg // 60)} min"
    if seg < 86400:
        return f"hace {seg // 3600} h"
    dias = seg // 86400
    return "ayer" if dias == 1 else f"hace {dias} días"


def puntuar(conv: dict, entrantes: list[dict], respondio_seguimiento: bool, ahora: datetime) -> tuple[int, list[str]]:
    """Devuelve (puntaje 0-100, razones). `entrantes` son los mensajes del
    prospecto de los últimos 7 días, del más viejo al más nuevo."""
    puntos, razones = 0, []
    ultimo_in = parse_ts(conv.get("last_inbound_at"))
    ultimo_msg = parse_ts(conv.get("last_message_at"))
    if ultimo_in:
        horas = (ahora - ultimo_in).total_seconds() / 3600
        if horas <= 24:
            puntos += 30
            razones.append(f"Escribió {_hace(ultimo_in, ahora)}")
        elif horas <= 72:
            puntos += 15
            razones.append(f"Escribió {_hace(ultimo_in, ahora)}")
        if ultimo_msg and ultimo_in >= ultimo_msg - timedelta(seconds=2) and horas <= 72:
            puntos += 15
            razones.insert(0, "Está esperando tu respuesta")
    n = len(entrantes)
    if n >= 3:
        puntos += min(20, n * 2)
        razones.append(f"{n} mensajes esta semana")
    if respondio_seguimiento:
        puntos += 20
        razones.append("Contestó tu seguimiento")
    vistos: list[str] = []
    for m in entrantes:
        texto = (m.get("body") or "").lower()
        for palabra, razon in INTENCION.items():
            if palabra in texto and razon not in vistos:
                vistos.append(razon)
    if vistos:
        puntos += min(25, 10 * len(vistos))
        razones.extend(vistos[:3])
    return min(100, puntos), razones


async def calientes(user_id: str, limite: int = 12) -> list[dict]:
    ahora = datetime.now(timezone.utc)
    desde = (ahora - timedelta(days=14)).isoformat()
    convs = await leer("wa2_conversaciones", {
        "user_id": f"eq.{user_id}", "last_inbound_at": f"gte.{desde}",
        "select": "id,contacto_id,numero_id,last_inbound_at,last_message_at",
        "order": "last_inbound_at.desc", "limit": "150"})
    if not convs:
        return []
    ids = [c["id"] for c in convs]
    semana = (ahora - timedelta(days=7)).isoformat()
    mensajes: dict[str, list[dict]] = {}
    for i in range(0, len(ids), 50):
        for m in await leer("wa2_mensajes", {
                "conversacion_id": en_lista(ids[i:i + 50]), "direction": "eq.in",
                "created_at": f"gte.{semana}", "select": "conversacion_id,body,created_at",
                "order": "created_at.asc", "limit": "3000"}):
            mensajes.setdefault(m["conversacion_id"], []).append(m)
    contactos = {c["id"]: c for c in await leer("wa2_contactos", {
        "id": en_lista({c["contacto_id"] for c in convs}), "select": "id,nombre,wa_id,opt_out"})}
    respondieron = {i["contacto_id"] for i in await leer("seg_inscripciones", {
        "user_id": f"eq.{user_id}", "estado": "eq.respondio", "respondio_en": f"gte.{semana}",
        "select": "contacto_id"})}
    salida = []
    for c in convs:
        contacto = contactos.get(c["contacto_id"]) or {}
        entrantes = mensajes.get(c["id"], [])
        puntos, razones = puntuar(c, entrantes, c["contacto_id"] in respondieron, ahora)
        if puntos < 20:
            continue
        ultimo = (entrantes[-1].get("body") if entrantes else "") or ""
        salida.append({
            "conversacion_id": c["id"], "contacto_id": c["contacto_id"],
            "nombre": (contacto.get("nombre") or "").strip() or contacto.get("wa_id") or "Sin nombre",
            "primer_nombre": primer_nombre(contacto.get("nombre")),
            "telefono": contacto.get("wa_id"), "puntaje": puntos, "razones": razones[:4],
            "ultimo_mensaje": ultimo[:160], "ultimo_en": c.get("last_inbound_at"),
        })
    salida.sort(key=lambda x: (x["puntaje"], x["ultimo_en"] or ""), reverse=True)
    return salida[:limite]
