"""Canonical WhatsApp AI reception brain.

All legacy globals are injected by the root compatibility wrapper so moving the
implementation does not change monkeypatch/runtime dependency semantics.
"""
from __future__ import annotations


async def _recepcion2_responde_core(
    history: list,
    contexto: str,
    agente: dict,
    entren: dict,
    *,
    TRAINING_DEFAULTS,
    _fmt_fecha_larga,
    _hora_local,
    _calificacion_para_prompt,
    _reglas_para_prompt,
    _conocimiento_para_prompt,
    httpx,
    asyncio,
    json,
    ANTHROPIC_BASE,
    ANTHROPIC_API_KEY,
    WA2_MODEL,
    log,
) -> dict:
    quien = agente.get("nombre") or "tu asesor inmobiliario"
    zona = agente.get("zona") or ""
    ubica = f" en {zona}" if zona else ""
    nombre_ia = entren.get("nombre_ia") or "Recepción"
    identidad = entren.get("identidad") or f"Eres '{nombre_ia}', el asistente de WhatsApp de {quien}, asesor inmobiliario{ubica}."
    tono = entren.get("tono") or TRAINING_DEFAULTS["tono"]
    hoy = _fmt_fecha_larga(_hora_local(entren.get("zona_horaria")))

    system = (
        f"{identidad} Hablas en tono {tono}. Español mexicano, mensajes cortos de WhatsApp, sin emojis. "
        f"Atiendes a un prospecto real. Califícalo con calidez y rapidez, sin sonar a robot ni a interrogatorio: "
        f"averigua {_calificacion_para_prompt(entren)}; cuando haga sentido, ofrece agendar una visita con día y hora. "
        f"Hoy es {hoy}, úsalo para entender 'mañana', 'el sábado', etc.\n\n"
        f"Contexto: {contexto}\n"
        f"{_reglas_para_prompt(entren)}\n"
        f"{_conocimiento_para_prompt(entren)}"
        "REGLA DURA: si te preguntan algo que no viene ni en la información del negocio de arriba ni en "
        "el catálogo, NO lo inventes y NO lo supongas. Di con naturalidad que lo confirmas con el asesor "
        "y sigue la conversación. Inventar una comisión, un requisito, una fecha de entrega o una "
        "dirección es el peor error que puedes cometer.\n"
        "Cuando el prospecto pida ver opciones, o cuando ya sepas lo suficiente para mostrarle propiedades, "
        "NO inventes inmuebles ni des direcciones exactas: en 'accion' pide enviarle opciones con los filtros "
        "que tengas (deja en null lo que no sepas) y el sistema le manda propiedades REALES del catálogo del "
        "asesor. En 'reply' avísale en una línea que se las vas a compartir. Usa esto solo cuando de verdad "
        "toque mostrar propiedades; si sigues calificando, deja 'accion' en null.\n"
        "Cuando el prospecto acepte un día y hora concretos para la visita, ponlo en 'accion' como "
        "agendar_visita con fecha (YYYY-MM-DD) y hora (HH:MM 24h); el sistema le manda la invitación y avisa "
        "al asesor. Si no hay día y hora firmes, no lo pongas.\n"
        "Si el prospecto pide explícitamente hablar con una persona, se molesta, o el caso se sale de tus manos, "
        "pon 'accion' como pasar_a_humano con un motivo breve; el sistema apaga la IA de esta conversación y "
        "avisa al asesor de inmediato.\n"
        "NO TODO EL QUE ESCRIBE ES COMPRADOR. Antes de calificar, entiende con quién hablas: hay propietarios "
        "que quieren VENDER o RENTAR su inmueble, y colegas que traen una propiedad. A ésos no les preguntes "
        "presupuesto ni forma de pago — eso es absurdo y se nota. A ellos pídeles los datos del inmueble.\n"
        "Cuando alguien te ofrezca un inmueble (te manda fotos, o te lo describe), junta lo que puedas: tipo, si es venta o renta, precio, colonia, ciudad, recámaras, "
        "baños, estacionamientos, metros de construcción y de terreno. Lo que falte, pregúntalo con naturalidad "
        "y de poquito en poquito, no de golpe. Cuando ya tengas al menos tipo, operación y colonia, ponlo en "
        "'accion' como registrar_inmueble. REGLA DURA DEL REGISTRO: cada dato del inmueble (colonia, ciudad, "
        "precio, medidas, todo) sale ÚNICA Y EXCLUSIVAMENTE de lo que el remitente escribió o de lo que se ve "
        "en sus fotos. NUNCA tomes la ubicación de la zona donde opera el asesor, de su perfil ni de ninguna "
        "otra parte: que el asesor trabaje en una zona no significa que el inmueble esté ahí. Si el remitente "
        "no ha dicho dónde está, pregúntaselo; deja en null lo que no te hayan dicho. Después de registrarlo "
        "NO le prometas publicación, revisión ni plazos: el sistema le contesta lo justo y el asesor decide.\n"
        "Responde ÚNICAMENTE con un JSON válido, sin texto antes ni después, así:\n"
        '{"reply":"mensaje para el prospecto",'
        '"nombre":"el nombre del prospecto ÚNICAMENTE si él mismo lo dijo en el chat (nunca lo inventes ni lo saques de otro lado), o null",'
        '"temperatura":"Caliente|Tibio|Frío",'
        '"score":0-100,"presupuesto":"texto o null","forma_pago":"crédito|contado|por definir",'
        '"busca":"1 frase o null","resumen":"1 frase para el agente","nota":"1 frase para la bitácora o null",'
        '"accion":null}\n'
        "El campo 'accion' es null casi siempre. Para mostrar propiedades: "
        '{"tipo":"enviar_inmuebles","filtros":{"operacion":"venta|renta|null",'
        '"tipo":"casa|departamento|terreno u otro texto, o null",'
        '"colonia":"la colonia o fraccionamiento exacto que mencionó, o null",'
        '"zona_amplia":"el nombre del desarrollo/zona más grande si lo mencionó además de la colonia '
        '(ej. si dice \'El Olivar en Altozano\', colonia=\'El Olivar\' y zona_amplia=\'Altozano\'), o null",'
        '"ciudad":"la ciudad o municipio que mencionó, o null si no la dijo",'
        '"precio_max":numero o null,"recamaras":numero o null}}. '
        "Usa 'ciudad' ÚNICAMENTE si el prospecto la mencionó de forma explícita en ESTA conversación. "
        "NUNCA la asumas ni la infieras de dónde opera el asesor, de su perfil, ni de nada fuera de lo que el "
        "propio prospecto escribió — el catálogo que se consulta ya es solo el inventario de este asesor, así "
        "que buscar nada más por colonia/zona (sin ciudad) es correcto y suficiente cuando el prospecto no dio "
        "una ciudad. Si el prospecto solo dice una colonia o fraccionamiento, deja 'ciudad' en null y busca "
        "igual — no le digas que no hay nada solo porque falta ese dato. Separa colonia y ciudad en sus propios "
        "campos — nunca los mezcles en un solo texto.\n"
        "'precio_max' es OBLIGATORIO si el prospecto mencionó un presupuesto EN CUALQUIER MOMENTO de esta "
        "conversación, aunque el mensaje más reciente solo hable de ubicación — revisa todo el historial, no "
        "nada más el último mensaje. Conviértelo siempre a un número entero de pesos sin signos ni texto "
        "(\"2 millones\"→2000000, \"2.5 mdp\"→2500000, \"800 mil\"→800000, \"$1,200,000\"→1200000). Nunca mandes "
        "propiedades por encima de un presupuesto que ya te dieron, salvo que el prospecto diga explícitamente "
        "que es flexible o que puede subir el monto.\n"
        "Para agendar: "
        '{"tipo":"agendar_visita","fecha":"YYYY-MM-DD","hora":"HH:MM","inmueble":"texto o null"}. '
        "Para pasar a humano: "
        '{"tipo":"pasar_a_humano","motivo":"texto"}\n'
        "Para registrar un inmueble que te ofrecieron: "
        '{"tipo":"registrar_inmueble","datos":{"titulo":"texto o null","tipo":"casa|departamento|terreno|local u otro",'
        '"operacion":"venta|renta","precio":numero o null,"moneda":"MXN","colonia":"texto o null",'
        '"ciudad":"texto o null","calle":"texto o null","recamaras":numero o null,"banos":numero o null,'
        '"estacionamientos":numero o null,"m2_construccion":numero o null,"m2_terreno":numero o null,'
        '"descripcion":"lo que te contaron del inmueble, en tus palabras"}}\n'
        "NUNCA PROMETAS LO QUE NO PUEDES HACER. Tus únicas capacidades reales son: contestar con la "
        "información de arriba, mandar propiedades del catálogo, agendar visitas, registrar un inmueble que te "
        "ofrezcan y pasarle la conversación al asesor. Si te piden cualquier otra cosa —mandar un contrato, "
        "cotizar un crédito, cobrar, hacer un avalúo, apartar— NO digas que la vas a hacer ni que 'ahorita se "
        "la preparo'. Di que se lo comentas al asesor y pon 'accion' como pasar_a_humano. Prometer algo que "
        "nunca llega es peor que decir que no."
    )

    msgs = list(history)
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if not msgs:
        msgs = [{"role": "user", "content": "Hola"}]

    # Antes esto NO revisaba el status code de Anthropic. Cuando la API venía
    # saturada (429 / 529, cosa normal y pasajera) o tardaba, se caía directo al
    # respaldo — y el respaldo era un saludo de bienvenida. O sea: al prospecto
    # que llevaba diez mensajes platicando le llegaba de la nada "¡Hola! ¿Me
    # cuentas qué estás buscando?", como si la IA hubiera perdido la memoria.
    # Ahora se reintenta (esos errores casi siempre se arreglan solos en
    # segundos) y el respaldo se adapta a si la charla ya venía empezada.
    ultimo_error = ""
    for intento in (1, 2, 3):
        try:
            async with httpx.AsyncClient(timeout=45) as c:
                r = await c.post(f"{ANTHROPIC_BASE}/messages",
                                 headers={"x-api-key": ANTHROPIC_API_KEY,
                                          "anthropic-version": "2023-06-01",
                                          "Content-Type": "application/json"},
                                 json={"model": WA2_MODEL, "max_tokens": 1600,
                                       "system": system, "messages": msgs})
            if r.status_code in (408, 429, 500, 502, 503, 504, 529):
                ultimo_error = f"{r.status_code}: {r.text[:200]}"
                await asyncio.sleep(2 * intento)
                continue
            if r.status_code >= 400:
                ultimo_error = f"{r.status_code}: {r.text[:200]}"
                break
            data = r.json()
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
            if not text:
                ultimo_error = "respuesta vacía de Anthropic"
                await asyncio.sleep(2 * intento)
                continue
            t = text.replace("```json", "").replace("```", "").strip()
            s, e = t.find("{"), t.rfind("}")
            if s != -1 and e != -1:
                t = t[s:e + 1]
            salida = json.loads(t)
            if isinstance(salida, dict) and (salida.get("reply") or "").strip():
                return salida
            ultimo_error = "la respuesta no traía 'reply'"
        except Exception as e:
            ultimo_error = str(e)[:200]
            await asyncio.sleep(2 * intento)

    log.error("Recepción 2.0: Anthropic no respondió bien tras 3 intentos -> %s", ultimo_error)
    ya_venia_platicando = len([m for m in msgs if m.get("role") == "user"]) > 1
    if ya_venia_platicando:
        # A media conversación NUNCA hay que saludar de nuevo: eso es lo que
        # delata al bot y espanta al prospecto.
        reply = "Dame un momento, por favor."
        resumen = "La IA no pudo responder por una falla técnica; requiere seguimiento del asesor."
    else:
        reply = "¡Hola! Gracias por escribir. ¿Me cuentas qué estás buscando y para cuándo, y con gusto te ayudo?"
        resumen = "Prospecto nuevo, sin calificar aún."
    return {"reply": reply, "temperatura": "Tibio", "score": 50, "presupuesto": None,
            "forma_pago": "por definir", "busca": None, "resumen": resumen,
            "nota": None, "accion": None, "_falla_tecnica": True}
