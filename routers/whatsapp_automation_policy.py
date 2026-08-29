"""Pure validation/normalization policy for WhatsApp automations."""
from __future__ import annotations


def _limpiar_automatizacion_core(req, *, _AUTO_TIPOS, _FLUJO_CAMPOS, HTTPException) -> dict:
    nombre = (req.nombre or "").strip()[:80]
    if not nombre:
        raise HTTPException(status_code=400, detail="Ponle un nombre a la automatización.")
    disparador = req.disparador if req.disparador in ("palabra", "nuevo", "nuevo_3m") else "palabra"
    palabras = []
    for p in (req.palabras or []):
        t = str(p).strip().lower()[:60]
        if t and t not in palabras:
            palabras.append(t)
    palabras = palabras[:15]
    if disparador == "palabra" and not palabras:
        raise HTTPException(status_code=400, detail="Escribe al menos una palabra que la dispare.")
    acciones = []
    for a in (req.acciones or []):
        tipo = str((a or {}).get("tipo") or "").strip()
        valor = str((a or {}).get("valor") or "").strip()
        if tipo not in _AUTO_TIPOS:
            continue
        paso: dict = {"tipo": tipo, "valor": valor}
        if tipo == "mensaje":
            paso["valor"] = valor[:1000]
            if not paso["valor"]:
                continue
        elif tipo == "etiqueta":
            paso["valor"] = valor[:40]
            if not paso["valor"]:
                continue
        elif tipo == "pregunta":
            paso["valor"] = valor[:1000]
            if not paso["valor"]:
                continue
            g = str((a or {}).get("guardar") or "nota").strip().lower()
            paso["guardar"] = g if g in _FLUJO_CAMPOS else "nota"
        elif tipo == "opciones":
            paso["valor"] = valor[:1000]
            ops = []
            for o in ((a or {}).get("opciones") or [])[:6]:
                txt = str((o or {}).get("texto") or "").strip()[:60]
                if not txt:
                    continue
                op: dict = {"texto": txt}
                try:
                    ir = int((o or {}).get("ir") or 0)
                except Exception:
                    ir = 0
                if ir > 0:
                    op["ir"] = ir  # número de paso (1-based) al que salta
                ops.append(op)
            if len(ops) < 2:
                continue  # un menú de una sola opción no es un menú
            paso["opciones"] = ops
        else:  # 'humano' / 'ia' no llevan valor
            paso["valor"] = ""
        acciones.append(paso)
    acciones = acciones[:12]
    if not acciones:
        raise HTTPException(status_code=400, detail="Agrega al menos un paso a la automatización.")
    return {"nombre": nombre, "numero_id": req.numero_id or None, "disparador": disparador,
            "palabras": palabras, "acciones": acciones, "activa": bool(req.activa)}
