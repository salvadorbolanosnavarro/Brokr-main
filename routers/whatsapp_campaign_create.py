from __future__ import annotations


async def wa2_campana_crear_core(req, request, background, *, _numero_visible,
                                 _audiencia_campana, WA2_CAMPANA_TOPE,
                                 HTTPException, _now, sb_post, _correr_campana):
    _, numero = await _numero_visible(request, req.numero_id)

    nombre = (req.nombre or "").strip()[:80]
    plantilla = (req.plantilla or "").strip()
    if not nombre or not plantilla:
        raise HTTPException(status_code=400, detail="Falta el nombre de la campaña o la plantilla.")

    etiqueta = (req.etiqueta or "").strip() or None
    audiencia = await _audiencia_campana(numero, etiqueta)
    if not audiencia:
        raise HTTPException(status_code=400,
                            detail="No hay contactos en esa audiencia (o todos pidieron baja).")
    if len(audiencia) > WA2_CAMPANA_TOPE:
        raise HTTPException(status_code=400,
                            detail=f"La audiencia tiene {len(audiencia)} contactos y el tope por "
                                   f"campaña es {WA2_CAMPANA_TOPE}. Usa una etiqueta para segmentarla.")

    variables = [str(v)[:200] for v in (req.variables or [])][:10]
    fila = {"user_id": numero["user_id"], "numero_id": numero["id"], "nombre": nombre,
            "plantilla": plantilla, "idioma": (req.idioma or "es_MX")[:12],
            "variables": variables, "etiqueta": etiqueta, "estado": "enviando",
            "total": len(audiencia), "enviados": 0, "fallidos": 0, "created_at": _now()}
    creado = await sb_post("wa2_campanas", fila)
    if not creado:
        raise HTTPException(status_code=500,
                            detail="No se pudo crear la campaña. ¿Ya corriste la migración de campañas?")
    campana_id = (creado[0] if isinstance(creado, list) else creado).get("id")

    background.add_task(_correr_campana, campana_id, numero, audiencia,
                        plantilla, (req.idioma or "es_MX"), variables)
    return {"ok": True, "campana_id": campana_id, "total": len(audiencia)}
