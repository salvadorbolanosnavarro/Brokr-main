"""Pure statistics aggregation for WhatsApp 2.0."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _dt(valor) -> datetime | None:
    """Parse a Postgres timestamptz without ever raising."""
    if not valor:
        return None
    try:
        txt = str(valor).replace("Z", "+00:00")
        d = datetime.fromisoformat(txt)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _mediana(nums: list) -> float | None:
    if not nums:
        return None
    s = sorted(nums)
    n = len(s)
    medio = n // 2
    return float(s[medio]) if n % 2 else (s[medio - 1] + s[medio]) / 2.0


def _agrega_ventana(dias: int, ahora_utc: datetime, zona: str,
                    contactos: list, conversaciones: list, mensajes: list,
                    numeros: list) -> dict:
    """Aggregate all WhatsApp metrics for one reporting window."""
    try:
        tz = ZoneInfo(zona)
    except Exception:
        tz = timezone.utc
    corte = ahora_utc - timedelta(days=dias) if dias else None

    def dentro(d: datetime | None) -> bool:
        if corte is None:
            return d is not None
        return d is not None and d >= corte

    serie: dict = {}
    heat = [[0] * 24 for _ in range(7)]
    tot = {"mensajes": 0, "entrantes": 0, "salientes": 0, "ia": 0, "agente": 0}
    por_conv: dict = {}
    for m in mensajes:
        d = _dt(m.get("created_at"))
        if not dentro(d):
            continue
        local = d.astimezone(tz)
        clave = local.date().isoformat()
        fila = serie.setdefault(clave, {"entrantes": 0, "ia": 0, "agente": 0})
        entrante = (m.get("direction") or "") == "in"
        sender = (m.get("sender") or "").lower()
        tot["mensajes"] += 1
        if entrante:
            tot["entrantes"] += 1
            fila["entrantes"] += 1
            heat[local.weekday()][local.hour] += 1
        else:
            tot["salientes"] += 1
            if sender == "ia":
                tot["ia"] += 1
                fila["ia"] += 1
            else:
                tot["agente"] += 1
                fila["agente"] += 1
        cid = m.get("conversacion_id")
        if cid:
            por_conv.setdefault(cid, []).append((d, entrante, sender))

    resp_todas, resp_ia, resp_agente, sin_responder = [], [], [], 0
    for cid, filas in por_conv.items():
        filas.sort(key=lambda x: x[0])
        if filas and filas[-1][1]:
            sin_responder += 1
        esperando = None
        for fecha, entrante, sender in filas:
            if entrante:
                if esperando is None:
                    esperando = fecha
            elif esperando is not None:
                minutos = max(0.0, (fecha - esperando).total_seconds() / 60.0)
                if minutos <= 60 * 72:
                    resp_todas.append(minutos)
                    (resp_ia if sender == "ia" else resp_agente).append(minutos)
                esperando = None

    temperatura: dict = {}
    etapa: dict = {}
    forma_pago: dict = {}
    scores: list = []
    score_buckets = {"0-24": 0, "25-49": 0, "50-74": 0, "75-100": 0}
    contactos_nuevos = 0
    for c in contactos:
        if dentro(_dt(c.get("created_at"))):
            contactos_nuevos += 1
        t = (c.get("temperatura") or "Nuevo").strip() or "Nuevo"
        temperatura[t] = temperatura.get(t, 0) + 1
        e = (c.get("etapa") or "Nuevo").strip() or "Nuevo"
        etapa[e] = etapa.get(e, 0) + 1
        fp = (c.get("forma_pago") or "Por definir").strip() or "Por definir"
        forma_pago[fp] = forma_pago.get(fp, 0) + 1
        sc = c.get("score")
        if isinstance(sc, (int, float)):
            scores.append(float(sc))
            if sc < 25:
                score_buckets["0-24"] += 1
            elif sc < 50:
                score_buckets["25-49"] += 1
            elif sc < 75:
                score_buckets["50-74"] += 1
            else:
                score_buckets["75-100"] += 1

    convs_nuevas = 0
    convs_activas = 0
    handoffs = 0
    propiedades: dict = {}
    por_numero: dict = {}
    dia_24h = ahora_utc - timedelta(hours=24)
    for cv in conversaciones:
        creada = _dt(cv.get("created_at"))
        ultimo = _dt(cv.get("last_message_at"))
        nueva = dentro(creada)
        movida = dentro(ultimo)
        if nueva:
            convs_nuevas += 1
        if ultimo and ultimo >= dia_24h:
            convs_activas += 1
        if movida and cv.get("ia_enabled") is False:
            handoffs += 1
        if movida:
            for p in (cv.get("ultimas_propiedades") or []):
                pid = p.get("id") if isinstance(p, dict) else p
                if not pid:
                    continue
                reg = propiedades.setdefault(str(pid), {"conversaciones": 0, "titulo": None})
                reg["conversaciones"] += 1
                if isinstance(p, dict) and p.get("titulo"):
                    reg["titulo"] = p.get("titulo")
        nid = cv.get("numero_id")
        if nid:
            reg = por_numero.setdefault(str(nid), {"conversaciones": 0, "nuevas": 0})
            if movida:
                reg["conversaciones"] += 1
            if nueva:
                reg["nuevas"] += 1

    conv_numero = {str(cv.get("id")): str(cv.get("numero_id") or "") for cv in conversaciones}
    msg_numero: dict = {}
    for cid, filas in por_conv.items():
        nid = conv_numero.get(str(cid))
        if not nid:
            continue
        reg = msg_numero.setdefault(nid, {"mensajes": 0, "entrantes": 0, "ia": 0})
        for _f, entrante, sender in filas:
            reg["mensajes"] += 1
            if entrante:
                reg["entrantes"] += 1
            elif sender == "ia":
                reg["ia"] += 1

    numeros_out = []
    for n in numeros:
        nid = str(n.get("id"))
        a = por_numero.get(nid, {"conversaciones": 0, "nuevas": 0})
        b = msg_numero.get(nid, {"mensajes": 0, "entrantes": 0, "ia": 0})
        salientes_n = b["mensajes"] - b["entrantes"]
        numeros_out.append({
            "id": nid,
            "alias": n.get("alias") or n.get("display_number") or "Número",
            "display_number": n.get("display_number"),
            "ia_enabled": n.get("ia_enabled") is not False,
            "conversaciones": a["conversaciones"],
            "nuevas": a["nuevas"],
            "mensajes": b["mensajes"],
            "entrantes": b["entrantes"],
            "pct_ia": round((b["ia"] / salientes_n) * 100) if salientes_n else 0,
        })
    numeros_out.sort(key=lambda x: x["mensajes"], reverse=True)

    salientes = tot["salientes"]
    return {
        "totales": {
            **tot,
            "conversaciones_nuevas": convs_nuevas,
            "conversaciones_activas_24h": convs_activas,
            "contactos_nuevos": contactos_nuevos,
            "handoffs": handoffs,
            "sin_responder": sin_responder,
            "pct_ia": round((tot["ia"] / salientes) * 100) if salientes else 0,
            "msgs_por_conversacion": round(tot["mensajes"] / len(por_conv), 1) if por_conv else 0,
        },
        "serie": [{"fecha": k, **v} for k, v in sorted(serie.items())],
        "heat": heat,
        "temperatura": temperatura,
        "etapa": etapa,
        "forma_pago": forma_pago,
        "score": {
            "promedio": round(sum(scores) / len(scores)) if scores else None,
            "buckets": score_buckets,
        },
        "respuesta_min": {
            "mediana": round(_mediana(resp_todas), 1) if resp_todas else None,
            "mediana_ia": round(_mediana(resp_ia), 1) if resp_ia else None,
            "mediana_agente": round(_mediana(resp_agente), 1) if resp_agente else None,
            "n": len(resp_todas),
        },
        "numeros": numeros_out,
        "propiedades": propiedades,
    }
