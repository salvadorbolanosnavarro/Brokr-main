"""WhatsApp advisor-mode DB tool execution."""
from __future__ import annotations


async def _asesor_ejecutar_tool_core(user_id: str, name: str, args: dict, zona: str | None,
                                     conversacion_id: str, *, sb_get, _hora_local, _now,
                                     sb_patch, _asesor_ctx_guardar, _fecha_hora_utc_iso,
                                     sb_post) -> str:
    if name == "buscar_contactos":
        q = (args.get("query") or "").replace(",", " ").strip()
        params = {"user_id": f"eq.{user_id}", "select": "id,nombre,telefono,tipo",
                  "order": "updated_at.desc", "limit": "8"}
        if q:
            params["or"] = f"(nombre.ilike.*{q}*,telefono.ilike.*{q}*,email.ilike.*{q}*,notas.ilike.*{q}*)"
        rows = await sb_get("contactos", params)
        if not rows:
            return "No encontré contactos que coincidan."
        return "\n".join(f"• id={c['id']} · {c.get('nombre') or 'Sin nombre'}"
                          + (f" · {c['telefono']}" if c.get("telefono") else "")
                          + (f" · {c['tipo']}" if c.get("tipo") else "")
                          for c in rows)

    if name == "buscar_tareas":
        q = (args.get("query") or "").replace(",", " ").strip()
        params = {"user_id": f"eq.{user_id}", "select": "id,titulo,fecha_entrega,completada",
                  "order": "created_at.desc", "limit": "8"}
        if q:
            params["or"] = f"(titulo.ilike.*{q}*,notas.ilike.*{q}*)"
        rows = await sb_get("tareas", params)
        if not rows:
            return "No encontré tareas que coincidan."
        return "\n".join(f"• id={t['id']} · {t.get('titulo') or 'Sin título'}"
                          + (" · completada" if t.get("completada") else " · pendiente")
                          + (f" · {str(t['fecha_entrega'])[:16].replace('T', ' ')} UTC"
                             if t.get("fecha_entrega") else "")
                          for t in rows)

    if name == "buscar_propiedades":
        q = (args.get("query") or "").replace(",", " ").strip()
        params = {"user_id": f"eq.{user_id}", "select": "id,titulo,colonia,ciudad,operacion,precio",
                  "order": "updated_at.desc", "limit": "8"}
        if q:
            params["or"] = (f"(titulo.ilike.*{q}*,colonia.ilike.*{q}*,calle.ilike.*{q}*,"
                            f"ciudad.ilike.*{q}*,clave_interna.ilike.*{q}*)")
        rows = await sb_get("propiedades", params)
        if not rows:
            return "No encontré propiedades que coincidan."
        return "\n".join(f"• id={p['id']} · {p.get('titulo') or 'Sin título'}"
                          + (f" · {p['colonia']}" if p.get("colonia") else "")
                          + (f", {p['ciudad']}" if p.get("ciudad") else "")
                          + (f" · {p['operacion']}" if p.get("operacion") else "")
                          for p in rows)

    if name == "agregar_comentario":
        destino = (args.get("destino") or "").strip().lower()
        fila_id = (args.get("id") or "").strip()
        comentario = (args.get("comentario") or "").strip()
        if destino not in ("contacto", "tarea", "propiedad") or not fila_id or not comentario:
            return "Faltan datos: necesito destino (contacto, tarea o propiedad), id y comentario."
        tabla = {"contacto": "contactos", "tarea": "tareas", "propiedad": "propiedades"}[destino]
        campo_nombre = "nombre" if tabla == "contactos" else "titulo"
        rows = await sb_get(tabla, {"id": f"eq.{fila_id}", "user_id": f"eq.{user_id}",
                                    "select": f"id,notas,{campo_nombre}", "limit": "1"})
        if not rows:
            return f"No encontré ese {destino} (id={fila_id}). Búscalo primero para usar el id exacto."
        etiqueta = rows[0].get(campo_nombre) or fila_id
        linea = f"[{_hora_local(zona).strftime('%d/%m %H:%M')} · Broq] {comentario}"
        notas = ((rows[0].get("notas") or "") + "\n" + linea).strip()
        cuerpo = {"notas": notas}
        if tabla in ("contactos", "propiedades"):
            cuerpo["updated_at"] = _now()
        ok = await sb_patch(tabla, {"id": f"eq.{fila_id}", "user_id": f"eq.{user_id}"}, cuerpo)
        if not ok:
            return "No se pudo guardar el comentario. Intenta de nuevo."
        await _asesor_ctx_guardar(conversacion_id, {f"ultimo_{destino}_id": fila_id,
                                                    f"ultimo_{destino}_nombre": etiqueta})
        return f"Listo, comentario agregado a {destino} '{etiqueta}': {linea}"

    if name == "crear_tarea":
        titulo = (args.get("titulo") or "").strip()
        if not titulo:
            return "Falta el título de la tarea."
        fila = {"user_id": user_id, "titulo": titulo,
                "notas": (args.get("notas") or "").strip() or None,
                "contacto_id": (args.get("contacto_id") or "").strip() or None,
                "propiedad_id": (args.get("propiedad_id") or "").strip() or None}
        if args.get("fecha"):
            fila["fecha_entrega"] = _fecha_hora_utc_iso(args["fecha"], args.get("hora") or "09:00", zona)
        creada = await sb_post("tareas", fila)
        if not creada:
            return "No se pudo crear la tarea. Intenta de nuevo."
        tarea_id = creada[0].get("id")
        if tarea_id and fila.get("contacto_id"):
            await sb_post("tareas_contactos", {"user_id": user_id, "tarea_id": tarea_id,
                                               "contacto_id": fila["contacto_id"]})
        if tarea_id and fila.get("propiedad_id"):
            await sb_post("tareas_propiedades", {"user_id": user_id, "tarea_id": tarea_id,
                                                 "propiedad_id": fila["propiedad_id"]})
        await _asesor_ctx_guardar(conversacion_id, {"ultima_tarea_id": tarea_id,
                                                    "ultima_tarea_titulo": titulo})
        return f"Tarea creada (id={tarea_id}): {titulo}" + (
            f" para el {args['fecha']} {args.get('hora') or ''}".rstrip() if args.get("fecha") else "")

    return "No reconozco esa herramienta."
