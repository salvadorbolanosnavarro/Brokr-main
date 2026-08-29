from __future__ import annotations


async def _entrenamiento_de_core(user_id: str, numero_id: str, *, sb_get, TRAINING_DEFAULTS) -> dict:
    rows = await sb_get("wa2_entrenamiento", {
        "user_id": f"eq.{user_id}", "numero_id": f"eq.{numero_id}", "select": "*", "limit": "1"})
    if rows:
        return rows[0]
    rows = await sb_get("wa2_entrenamiento", {
        "user_id": f"eq.{user_id}", "numero_id": "is.null", "select": "*", "limit": "1"})
    if rows:
        return rows[0]
    return dict(TRAINING_DEFAULTS)


async def _generar_ficha_pdf_core(p_ficha: dict, *, httpx, BROQUER_API_BASE, log) -> tuple[str | None, str | None]:
    """Llama al MISMO generador de PDF (Playwright) que usa el módulo de
    Ficha técnica — no se reescribe nada, solo se usa por HTTP. Devuelve
    (url_publica, filename) o (None, None) si no se pudo generar a tiempo."""
    try:
        async with httpx.AsyncClient(timeout=45) as c:
            r = await c.post(f"{BROQUER_API_BASE}/ficha-pdf", json=p_ficha)
        if r.status_code >= 400:
            log.warning("No se pudo generar la ficha PDF: %s %s", r.status_code, r.text[:200])
            return None, None
        d = r.json()
        token = d.get("token")
        if not token:
            return None, None
        return f"{BROQUER_API_BASE}/ficha-pdf/{token}", d.get("filename") or "ficha.pdf"
    except Exception as e:
        log.warning("Timeout/error generando ficha PDF: %s", e)
        return None, None


async def _wa_send_document_link_core(numero: dict, wa_id: str, url: str, filename: str, caption: str = "", *, httpx, GRAPH_API, log) -> str | None:
    """Manda un documento por URL pública directa (sin subirlo primero) —
    válido porque /ficha-pdf/{token} ya es una URL pública servida por Broquer."""
    if not numero.get("access_token"):
        return None
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{GRAPH_API}/{numero['phone_number_id']}/messages",
                         headers={"Authorization": f"Bearer {numero['access_token']}"},
                         json={"messaging_product": "whatsapp", "to": wa_id, "type": "document",
                               "document": {"link": url, "filename": filename, "caption": caption[:1024]}})
        if r.status_code >= 400:
            log.error("Envío de ficha PDF falló (%s): %s", numero["phone_number_id"], r.text[:300])
            return None
        d = r.json()
        msgs = d.get("messages") or []
        return msgs[0].get("id") if msgs else None
