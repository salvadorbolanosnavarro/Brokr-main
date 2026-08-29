"""Exact HTTP webhook entrypoints extracted from whatsapp.py."""


def wa2_verify_webhook_core(request, *, WA2_VERIFY_TOKEN, Response):
    p = request.query_params
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == WA2_VERIFY_TOKEN:
        return Response(content=p.get("hub.challenge", ""), media_type="text/plain")
    return Response(content="forbidden", status_code=403)


async def wa2_receive_webhook_core(
    request, background, *, WA2_APP_SECRET, log, Response, hmac, hashlib, json,
    _persistir_entrantes, _procesar_en_segundo_plano,
):
    raw = await request.body()

    # Sin secreto NO se procesa nada. Antes esto dejaba pasar todo cuando la
    # variable faltaba: cualquiera en internet podía inyectar mensajes falsos,
    # hacer que la IA contestara sola y quemar la cuenta de Anthropic.
    # Ahora se cierra la puerta y se grita en el log.
    if not WA2_APP_SECRET:
        log.error("WA_APP_SECRET y META_APP_SECRET vacíos: el webhook de WhatsApp "
                  "queda CERRADO hasta que se configure uno de los dos en Railway.")
        return Response(status_code=503)

    sig = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(WA2_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        log.warning("Firma de webhook 2.0 inválida")
        return Response(status_code=403)

    try:
        payload = json.loads(raw)
    except Exception:
        return Response(status_code=200)

    try:
        ok, trabajo = await _persistir_entrantes(payload)
    except Exception as e:
        log.exception("persistir_entrantes (2.0) reventó, pido reintento a Meta: %s", e)
        return Response(status_code=503)
    if not ok:
        return Response(status_code=503)

    for item in trabajo:
        background.add_task(_procesar_en_segundo_plano, item)

    return Response(status_code=200)
