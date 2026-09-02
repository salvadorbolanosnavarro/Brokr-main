"""Canonical WhatsApp CRM contact creation and synchronization."""
from __future__ import annotations


async def _crear_contacto_crm_core(
    user_id: str,
    wa_id: str,
    nombre: str | None,
    *,
    datetime,
    timezone,
    _normaliza_mx,
    get_org_context,
    _now,
    sb_post,
    log,
) -> str | None:
    """Crea el Contacto real en el CRM (tabla `contactos`, la misma de
    Contactos/Leads/Estadísticas) para un prospecto nuevo de WhatsApp.
    Sigue la MISMA convención de id que usa contactos.html ('c_' + timestamp
    en milisegundos), porque esa columna es TEXT, no uuid."""
    contacto_id = f"c_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    telefono = _normaliza_mx(wa_id)
    # Igual que en _alta_inmueble: sin org_id explícito, el contacto queda
    # huérfano de empresa y no se puede eliminar desde la plataforma.
    ctx_org = await get_org_context(user_id)
    org_id = (ctx_org or {}).get("org_id")
    fila = {
        "id": contacto_id, "user_id": user_id, "org_id": org_id,
        "nombre": (nombre or telefono or "Prospecto de WhatsApp").upper(),
        "telefono": telefono, "wa": telefono,
        "tipo": "comprador", "fuente": "WhatsApp",
        "notas": "Prospecto creado automáticamente por WhatsApp.",
        "es_potencial": True, "etiquetas": ["WhatsApp"],
        "operaciones": [],
        "created_at": _now(), "updated_at": _now(),
    }
    creado = await sb_post("contactos", fila)
    if not creado:
        log.error("No se pudo crear el Contacto en el CRM para wa_id=%s (user=%s)", wa_id, user_id)
        return None
    return contacto_id


async def _sincronizar_contacto_crm_core(
    user_id: str,
    contacto_wa2: dict,
    resultado_ia: dict | None = None,
    *,
    _now,
    sb_get,
    _hora_local,
    sb_patch,
    log,
) -> None:
    """Mantiene al día el Contacto real del CRM con lo que la IA va calificando:
    - Notas (historial): se le agrega una línea nueva cada vez (no se borra).
    - Descripción privada: es una FOTO del momento — se sobrescribe con lo
      último que se sabe del prospecto (temperatura, score, presupuesto,
      forma de pago, qué busca, resumen). No es historial, es el estado actual.
    Nunca truena el webhook si el CRM no responde — esto es un espejo, no la
    fuente de verdad de WhatsApp."""
    crm_id = contacto_wa2.get("contacto_crm_id")
    if not crm_id or not resultado_ia:
        return
    try:
        cambios = {"updated_at": _now()}
        busca = (resultado_ia.get("busca") or "").strip().lower()
        if "rent" in busca:
            cambios["tipo"] = "arrendatario"
        elif busca:
            cambios["tipo"] = "comprador"
        nombre_chat_crm = (resultado_ia.get("nombre") or "").strip()
        if nombre_chat_crm:
            cambios["nombre"] = nombre_chat_crm.upper()
        nota = resultado_ia.get("nota") or resultado_ia.get("resumen")
        if nota:
            rows = await sb_get("contactos", {"id": f"eq.{crm_id}", "select": "notas", "limit": "1"})
            previas = (rows[0].get("notas") or "") if rows else ""
            fecha = _hora_local().strftime("%d/%m %H:%M")
            cambios["notas"] = (previas + f"\n[{fecha} · WhatsApp] {nota}").strip()

        renglones = []
        if contacto_wa2.get("temperatura"): renglones.append(f"Temperatura: {contacto_wa2['temperatura']}")
        if contacto_wa2.get("score") is not None: renglones.append(f"Score: {contacto_wa2['score']}")
        if contacto_wa2.get("presupuesto"): renglones.append(f"Presupuesto: {contacto_wa2['presupuesto']}")
        if contacto_wa2.get("forma_pago"): renglones.append(f"Forma de pago: {contacto_wa2['forma_pago']}")
        if contacto_wa2.get("busca"): renglones.append(f"Busca: {contacto_wa2['busca']}")
        if contacto_wa2.get("resumen"): renglones.append(f"Resumen: {contacto_wa2['resumen']}")
        if renglones:
            cambios["descripcion_privada"] = "\n".join(renglones)

        await sb_patch("contactos", {"id": f"eq.{crm_id}"}, cambios)
    except Exception as e:
        log.warning("No se pudo sincronizar el Contacto %s del CRM: %s", crm_id, e)
