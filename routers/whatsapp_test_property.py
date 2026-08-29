"""Exact WhatsApp test-bench and property draft creation cores."""


async def wa2_probar_core(
    req, request, *, _require_user, _ids_visibles, sb_get, _in_filter,
    HTTPException, _entrenamiento_de, _perfil_agente, HISTORY_LIMIT,
    recepcion2_responde, _parsear_presupuesto, _buscar_inmuebles, _texto_inmueble,
):
    """Banco de pruebas: platica con la IA EXACTAMENTE como lo haría un
    prospecto, con el entrenamiento y el catálogo reales, pero sin mandar un
    solo WhatsApp a nadie, sin crear contactos y sin tocar la base.

    Hasta ahora la única forma de saber si el entrenamiento quedó bien era
    esperar a que llegara un prospecto de verdad y rezar. Eso es justo lo que
    no puede pasar el día del lanzamiento con AMPI."""
    user_id = await _require_user(request)

    numero_id = req.numero_id or ""
    if numero_id:
        ids = await _ids_visibles(user_id)
        n = await sb_get("wa2_numeros", {"id": f"eq.{numero_id}", "user_id": _in_filter(ids),
                                         "select": "id,user_id", "limit": "1"})
        if not n:
            raise HTTPException(status_code=404, detail="Número no encontrado")
        dueño = n[0]["user_id"]
    else:
        dueño = user_id

    entren = await _entrenamiento_de(dueño, numero_id)
    agente = await _perfil_agente(dueño)

    history = []
    for h in (req.historial or [])[-HISTORY_LIMIT:]:
        texto = (h.get("texto") or "").strip()
        if not texto:
            continue
        history.append({"role": "assistant" if h.get("rol") == "ia" else "user", "content": texto})
    history.append({"role": "user", "content": req.mensaje})

    contexto = (f"Atiendes prospectos de {agente['nombre']}, asesor inmobiliario"
                f"{(' en ' + agente['zona']) if agente['zona'] else ''}. "
                "Si no sabes por qué propiedad escribe, pregúntale qué busca.")

    resultado = await recepcion2_responde(history, contexto, agente, entren)

    # Si la IA quiso mandar propiedades, se hace la MISMA búsqueda real contra
    # el catálogo, para que se vea si de verdad encuentra lo que debería.
    propiedades, aviso = [], None
    accion = resultado.get("accion")
    if isinstance(accion, dict) and accion.get("tipo") == "enviar_inmuebles":
        filtros = accion.get("filtros") or {}
        if not filtros.get("precio_max"):
            respaldo = _parsear_presupuesto(resultado.get("presupuesto") or "")
            if respaldo:
                filtros = {**filtros, "precio_max": respaldo}
        props, sin_resultados = await _buscar_inmuebles(dueño, filtros)
        propiedades = [{"id": p.get("id"), "titulo": p.get("titulo") or p.get("tipo"),
                        "resumen": _texto_inmueble(p).replace("\n", " · ")} for p in props[:3]]
        if sin_resultados:
            aviso = ("La IA buscó en tu catálogo y no encontró nada en esa zona. "
                     "Al prospecto real le avisaría con honestidad, sin ofrecerle otra ubicación.")
        filtros_usados = filtros
    else:
        filtros_usados = None

    return {
        "reply": resultado.get("reply"),
        "temperatura": resultado.get("temperatura"),
        "score": resultado.get("score"),
        "presupuesto": resultado.get("presupuesto"),
        "forma_pago": resultado.get("forma_pago"),
        "busca": resultado.get("busca"),
        "resumen": resultado.get("resumen"),
        "accion": accion,
        "filtros": filtros_usados,
        "propiedades": propiedades,
        "aviso": aviso,
        "falla_tecnica": bool(resultado.get("_falla_tecnica")),
    }


async def _alta_inmueble_core(
    user_id: str, datos: dict, wa_id: str, fotos: list | None = None, *,
    get_org_context, _normaliza_mx, _hora_local, _now, sb_post, log,
) -> str | None:
    """Da de alta un inmueble que un tercero le mandó al asesor por WhatsApp.

    Nace SIEMPRE con estatus 'no_activa': no aparece en el sitio público del
    asesor, no se le ofrece a ningún comprador y no se sincroniza a ningún
    lado. Es un borrador que espera revisión humana. Un dato que llegó por
    WhatsApp de alguien que no conocemos no puede tratararse como inventario
    real: ni el precio, ni la titularidad, ni siquiera que la casa exista
    están verificados.
    """
    tipo = (datos.get("tipo") or "").strip() or "Propiedad"
    colonia = (datos.get("colonia") or "").strip()
    operacion = (datos.get("operacion") or "").strip().lower()
    if operacion not in ("venta", "renta"):
        operacion = "venta"

    titulo = (datos.get("titulo") or "").strip() or \
        " ".join(x for x in [tipo, "en", operacion, ("· " + colonia) if colonia else ""] if x).strip()

    try:
        precio = float(datos.get("precio")) if datos.get("precio") not in (None, "") else None
    except Exception:
        precio = None

    def _entero(v):
        try:
            return int(float(v))
        except Exception:
            return None

    # org_id explícito: estas filas nacen con la service key, así que la base
    # NO puede deducir la empresa por la sesión (no hay sesión). Sin esto, el
    # inmueble queda huérfano de empresa y el dueño no puede ni borrarlo.
    ctx_org = await get_org_context(user_id)
    org_id = (ctx_org or {}).get("org_id")

    fila = {
        "user_id": user_id,
        "org_id": org_id,
        "titulo": titulo[:200],
        "tipo": tipo,
        "operacion": operacion,
        "precio": precio,
        "moneda": (datos.get("moneda") or "MXN").upper()[:4],
        "colonia": colonia or None,
        "ciudad": (datos.get("ciudad") or "").strip() or None,
        "calle": (datos.get("calle") or "").strip() or None,
        "recamaras": _entero(datos.get("recamaras")),
        "banos": _entero(datos.get("banos")),
        "estacionamientos": _entero(datos.get("estacionamientos")),
        "m2_construccion": _entero(datos.get("m2_construccion")),
        "m2_terreno": _entero(datos.get("m2_terreno")),
        "descripcion": (datos.get("descripcion") or "").strip() or None,
        "fotos": [f for f in (fotos or []) if f][:20],
        "estatus": "no_activa",
        "descripcion_privada": (
            f"Alta automática desde WhatsApp ({_normaliza_mx(wa_id)}) el "
            f"{_hora_local().strftime('%d/%m/%Y %H:%M')}. "
            "Datos proporcionados por un tercero, SIN VERIFICAR. "
            "Revisa precio, ubicación, medidas y titularidad antes de activarla."),
        "created_at": _now(),
        "updated_at": _now(),
    }
    creada = await sb_post("propiedades", fila)
    if not creada:
        log.error("No se pudo dar de alta el inmueble de WhatsApp (user=%s)", user_id)
        return None
    return creada[0].get("id")
