from __future__ import annotations


async def _wa_send_text_detallado_core(numero: dict, wa_id: str, texto: str, *, httpx, GRAPH_API, log, _revisar_token):
    """Como _wa_send_text, pero además regresa el error real de Meta (código y
    mensaje) cuando falla — necesario para distinguir 'ventana de 24h cerrada'
    (código 131047) de cualquier otro problema, en vez de tragarse el error."""
    if not numero.get("access_token"):
        return None, {"code": None, "message": "Este número no tiene un token de acceso válido."}
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{GRAPH_API}/{numero['phone_number_id']}/messages",
                         headers={"Authorization": f"Bearer {numero['access_token']}"},
                         json={"messaging_product": "whatsapp", "to": wa_id,
                               "type": "text", "text": {"body": texto, "preview_url": False}})
        if r.status_code >= 400:
            log.error("Envío de texto falló (%s): %s", numero["phone_number_id"], r.text[:300])
            try:
                err = (r.json().get("error") or {})
            except Exception:
                err = {}
            detalle = {"code": err.get("code"), "message": err.get("message") or "No se pudo enviar el mensaje."}
            await _revisar_token(numero, detalle)
            return None, detalle
        d = r.json()
        msgs = d.get("messages") or []
        return (msgs[0].get("id") if msgs else None), None


async def _wa_send_text_core(numero: dict, wa_id: str, texto: str, *, WA_MAX_TEXTO, _wa_send_text_detallado):
    """Manda texto. Si se pasa del tope de WhatsApp lo parte en varios mensajes:
    antes, un texto de más de 4096 caracteres hacía que Meta rechazara el envío
    COMPLETO y el prospecto no recibiera absolutamente nada."""
    texto = (texto or "").strip()
    if not texto:
        return None
    if len(texto) <= WA_MAX_TEXTO:
        wamid, _ = await _wa_send_text_detallado(numero, wa_id, texto)
        return wamid
    partes, actual = [], ""
    for parrafo in texto.split("\n"):
        if len(actual) + len(parrafo) + 1 > WA_MAX_TEXTO:
            if actual:
                partes.append(actual)
            actual = parrafo[:WA_MAX_TEXTO]
        else:
            actual = (actual + "\n" + parrafo) if actual else parrafo
    if actual:
        partes.append(actual)
    ultimo = None
    for parte in partes:
        ultimo, _ = await _wa_send_text_detallado(numero, wa_id, parte)
    return ultimo


async def _wa_marcar_leido_core(numero: dict, wamid: str | None, escribiendo: bool = True, *, httpx, GRAPH_API, log) -> None:
    """Pone la palomita azul y muestra 'escribiendo…' del lado del prospecto.

    Sin esto la conversación se siente falsa por los dos lados: el prospecto ve
    que sus mensajes nunca se marcan como leídos y luego, de golpe, aparece una
    respuesta larguísima escrita en cero segundos. Con esto se lee igual que un
    humano contestando desde su celular. Nunca debe tumbar nada si falla."""
    if not wamid or not numero.get("access_token"):
        return
    cuerpo = {"messaging_product": "whatsapp", "status": "read", "message_id": wamid}
    if escribiendo:
        cuerpo["typing_indicator"] = {"type": "text"}
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            await c.post(f"{GRAPH_API}/{numero['phone_number_id']}/messages",
                         headers={"Authorization": f"Bearer {numero['access_token']}"},
                         json=cuerpo)
    except Exception as e:
        log.debug("No se pudo marcar como leído: %s", e)


async def _descargar_media_core(numero: dict, media_id: str, *, httpx, GRAPH_API, log) -> tuple[bytes | None, str]:
    """Baja un archivo que mandó el prospecto (nota de voz, foto, documento).
    Meta lo entrega en dos pasos: primero la URL temporal, luego el binario —
    y ambos requieren el token del número. Devuelve (bytes, mime)."""
    if not media_id or not numero.get("access_token"):
        return None, ""
    headers = {"Authorization": f"Bearer {numero['access_token']}"}
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.get(f"{GRAPH_API}/{media_id}", headers=headers)
            if r.status_code >= 400:
                log.warning("No se pudo obtener la media %s: %s", media_id, r.text[:200])
                return None, ""
            info = r.json()
            url, mime = info.get("url"), info.get("mime_type") or ""
            if not url:
                return None, ""
            rb = await c.get(url, headers=headers)
            if rb.status_code >= 400 or not rb.content:
                return None, ""
            return rb.content, mime
    except Exception as e:
        log.warning("Error bajando media %s: %s", media_id, e)
        return None, ""


async def _transcribir_audio_core(contenido: bytes, mime: str, *, GROQ_API_KEY, httpx, GROQ_BASE, log) -> str:
    """Convierte una nota de voz en texto con Whisper (el mismo Groq que ya usa
    Broquer). Esto NO es un lujo: en México el prospecto manda audios todo el
    tiempo, y hasta ahora la IA solo veía la palabra '[audio]' y contestaba a
    ciegas —o peor, contestaba cualquier cosa— sin haber oído nada."""
    if not GROQ_API_KEY or not contenido:
        return ""
    ext = "ogg"
    if "mp4" in mime or "m4a" in mime:
        ext = "m4a"
    elif "mpeg" in mime or "mp3" in mime:
        ext = "mp3"
    elif "wav" in mime:
        ext = "wav"
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(f"{GROQ_BASE}/audio/transcriptions",
                             headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                             data={"model": "whisper-large-v3", "language": "es",
                                   "response_format": "json"},
                             files={"file": (f"nota.{ext}", contenido, mime or "audio/ogg")})
        if r.status_code >= 400:
            log.warning("Whisper falló: %s %s", r.status_code, r.text[:200])
            return ""
        return (r.json().get("text") or "").strip()
    except Exception as e:
        log.warning("Error transcribiendo audio: %s", e)
        return ""


async def _describir_imagen_core(contenido: bytes, mime: str, *, ANTHROPIC_API_KEY, httpx,
                                 ANTHROPIC_BASE, WA2_MODEL, log) -> str:
    """Le pide a Claude que lea la foto que mandó el prospecto (una captura de
    un anuncio, la fachada de la casa que quiere vender, un comprobante…).
    Antes la IA recibía literalmente '[image]' y le respondía de adivinanza."""
    if not ANTHROPIC_API_KEY or not contenido or len(contenido) > 4_500_000:
        return ""
    import base64
    if mime not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        mime = "image/jpeg"
    try:
        async with httpx.AsyncClient(timeout=40) as c:
            r = await c.post(f"{ANTHROPIC_BASE}/messages",
                             headers={"x-api-key": ANTHROPIC_API_KEY,
                                      "anthropic-version": "2023-06-01",
                                      "Content-Type": "application/json"},
                             json={"model": WA2_MODEL, "max_tokens": 300, "messages": [{
                                 "role": "user", "content": [
                                     {"type": "image", "source": {"type": "base64",
                                      "media_type": mime,
                                      "data": base64.b64encode(contenido).decode()}},
                                     {"type": "text", "text":
                                      "Describe en dos o tres frases, en español, qué se ve en esta "
                                      "imagen que un prospecto le mandó por WhatsApp a un asesor "
                                      "inmobiliario. Si hay texto legible (precios, direcciones, datos), "
                                      "transcríbelo. Solo la descripción, sin preámbulo."}]}]})
        if r.status_code >= 400:
            return ""
        data = r.json()
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    except Exception as e:
        log.warning("No se pudo describir la imagen: %s", e)
        return ""


async def _wa_send_image_core(numero: dict, wa_id: str, url: str, caption: str = "", *, httpx, GRAPH_API, log) -> str | None:
    if not numero.get("access_token"):
        return None
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{GRAPH_API}/{numero['phone_number_id']}/messages",
                         headers={"Authorization": f"Bearer {numero['access_token']}"},
                         json={"messaging_product": "whatsapp", "to": wa_id,
                               "type": "image", "image": {"link": url, "caption": caption[:1024]}})
        if r.status_code >= 400:
            log.error("Envío de imagen falló (%s): %s", numero["phone_number_id"], r.text[:300])
            return None
        d = r.json()
        msgs = d.get("messages") or []
        return msgs[0].get("id") if msgs else None


async def _wa_send_document_core(numero: dict, wa_id: str, contenido: bytes, filename: str, caption: str, *, httpx, GRAPH_API, log) -> None:
    """Sube el .ics como media y lo manda como documento adjunto."""
    if not numero.get("access_token"):
        return
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            up = await c.post(f"{GRAPH_API}/{numero['phone_number_id']}/media",
                              headers={"Authorization": f"Bearer {numero['access_token']}"},
                              data={"messaging_product": "whatsapp", "type": "text/calendar"},
                              files={"file": (filename, contenido, "text/calendar")})
            media_id = up.json().get("id") if up.status_code < 300 else None
            if not media_id:
                return
            await c.post(f"{GRAPH_API}/{numero['phone_number_id']}/messages",
                        headers={"Authorization": f"Bearer {numero['access_token']}"},
                        json={"messaging_product": "whatsapp", "to": wa_id, "type": "document",
                              "document": {"id": media_id, "filename": filename, "caption": caption}})
    except Exception as e:
        log.warning("No se pudo mandar el .ics: %s", e)
