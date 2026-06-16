# =============================================================================
# Broquer · Módulo WhatsApp (Recepción) — versión amarrada a TU stack
# -----------------------------------------------------------------------------
# Hecho con tus mismos patrones de main.py:
#   - httpx (async) para todo  ->  CERO dependencias nuevas
#   - Supabase por REST directo (apikey + service key), igual que tus helpers
#   - El cerebro corre en Anthropic (claude-sonnet-4-6), tu misma llamada
#   - Reusa el patrón de get_user_id_from_token para la bandeja
#
# Conectar en main.py:
#   from whatsapp import router as whatsapp_router
#   app.include_router(whatsapp_router)
#
# Webhook:  https://TU-APP.railway.app/whatsapp/webhook
# =============================================================================

import os
import json
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request, Response, BackgroundTasks, HTTPException
from pydantic import BaseModel

log = logging.getLogger("broquer.whatsapp")

# -----------------------------------------------------------------------------
# CONFIG  (tus mismos nombres de variables de entorno)
# -----------------------------------------------------------------------------
SUPABASE_URL         = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY    = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "") or SUPABASE_ANON_KEY

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE    = os.environ.get("ANTHROPIC_BASE", "https://api.anthropic.com/v1")
RECEPCION_MODEL   = os.environ.get("RECEPCION_MODEL", "claude-sonnet-4-6")

GRAPH_API        = "https://graph.facebook.com/v21.0"
WHATSAPP_TOKEN   = os.environ.get("WHATSAPP_TOKEN", "")
WA_VERIFY_TOKEN  = os.environ.get("WA_VERIFY_TOKEN", "broquer_verify")
WA_APP_SECRET    = os.environ.get("WA_APP_SECRET", "")

# Piloto (Grupo Navarro): si un número no está mapeado en wa_numbers, usamos esto
DEFAULT_USER_ID = os.environ.get("DEFAULT_USER_ID", "")
DEFAULT_AGENCIA = os.environ.get("DEFAULT_AGENCIA", "Grupo Navarro")

HISTORY_LIMIT = 14
router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# Helpers de Supabase (REST, con tu mismo patrón de headers)
# =============================================================================
def _sb_headers() -> dict:
    return {"apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json"}


async def sb_get(table: str, params: dict) -> list:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=_sb_headers(), params=params)
        return r.json() if r.status_code < 300 else []


async def sb_post(table: str, body: dict, prefer: str = "return=representation") -> list:
    async with httpx.AsyncClient(timeout=15) as c:
        h = _sb_headers(); h["Prefer"] = prefer
        r = await c.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, json=body)
        try:
            return r.json()
        except Exception:
            return []


async def sb_patch(table: str, params: dict, body: dict) -> list:
    async with httpx.AsyncClient(timeout=15) as c:
        h = _sb_headers(); h["Prefer"] = "return=representation"
        r = await c.patch(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, params=params, json=body)
        try:
            return r.json()
        except Exception:
            return []


# Igual que tu helper en main.py: saca el user_id del token de Supabase
async def get_user_id_from_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{SUPABASE_URL}/auth/v1/user",
                            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"})
            if r.status_code == 200:
                return r.json().get("id")
    except Exception:
        pass
    return None


# =============================================================================
# 1) WEBHOOK
# =============================================================================
@router.get("/webhook")
def verify_webhook(request: Request):
    p = request.query_params
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == WA_VERIFY_TOKEN:
        return Response(content=p.get("hub.challenge", ""), media_type="text/plain")
    return Response(content="forbidden", status_code=403)


@router.post("/webhook")
async def receive_webhook(request: Request, background: BackgroundTasks):
    raw = await request.body()

    if WA_APP_SECRET:
        import hmac, hashlib
        sig = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(WA_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            log.warning("Firma de webhook inválida")
            return Response(status_code=403)

    try:
        payload = json.loads(raw)
    except Exception:
        return Response(status_code=200)

    background.add_task(process_payload, payload)   # contestamos 200 ya; procesamos atrás
    return Response(status_code=200)


# =============================================================================
# 2) PROCESAMIENTO
# =============================================================================
async def process_payload(payload: dict):
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                field = change.get("field")
                value = change.get("value", {})
                if field == "messages":
                    await process_change(value)            # mensaje ENTRANTE del cliente
                elif field == "smb_message_echoes":
                    await process_echo(value)              # COEXISTENCE: el agente desde su celular
                elif field in ("history", "smb_app_state_sync"):
                    log.info("Coexistence sync '%s' recibido.", field)  # opcional: precargar historial
    except Exception as e:
        log.exception("Error procesando webhook: %s", e)


async def process_change(value: dict):
    metadata = value.get("metadata", {})
    phone_number_id = metadata.get("phone_number_id")
    user_id = await resolve_user(phone_number_id)
    if not user_id:
        log.warning("Sin user_id para phone_number_id=%s (configura wa_numbers o DEFAULT_USER_ID)", phone_number_id)
        return

    contacts = value.get("contacts", [])
    profile_name = contacts[0].get("profile", {}).get("name") if contacts else None

    for msg in value.get("messages", []):
        wamid = msg.get("id")
        if not wamid or await already_processed(wamid):
            continue

        from_wa = msg.get("from")
        referral = msg.get("referral")

        if msg.get("type") != "text":
            body = f"[{msg.get('type')}]"
            contact = await upsert_contact(user_id, from_wa, profile_name)
            conv = await get_or_create_conversation(user_id, contact, referral, phone_number_id)
            await store_message(user_id, contact["id"], conv["id"], wamid, "in", "lead", body)
            if conv.get("ai_enabled", True):
                await wa_send_text(phone_number_id, from_wa,
                                   "Gracias por tu mensaje. Por aquí te leo mejor en texto, "
                                   "¿me cuentas qué estás buscando?")
            continue

        body = msg.get("text", {}).get("body", "").strip()
        contact = await upsert_contact(user_id, from_wa, profile_name)
        conv = await get_or_create_conversation(user_id, contact, referral, phone_number_id)
        await store_message(user_id, contact["id"], conv["id"], wamid, "in", "lead", body)

        if not conv.get("ai_enabled", True):
            continue  # el agente tomó el control

        history = await fetch_history(conv["id"])
        result = await recepcion_responde(history, conv.get("property_ctx"))
        reply = (result or {}).get("reply")

        # anti-choque: si el agente contestó desde su cel mientras tanto, la IA ya no manda
        if reply and await ai_sigue_encendida(conv["id"]):
            sent = await wa_send_text(phone_number_id, from_wa, reply)
            out_id = (sent.get("messages") or [{}])[0].get("id")
            await store_message(user_id, contact["id"], conv["id"], out_id or f"local-{wamid}", "out", "ai", reply)

        await actualizar_calificacion(contact["id"], result)


async def process_echo(value: dict):
    """COEXISTENCE: el agente respondió desde la app de WhatsApp en su celular.
    Lo guardamos como mensaje del agente y APAGAMOS la IA en esa conversación.
    (La estructura del echo puede variar; se lee defensivo y se loguea el crudo.)"""
    metadata = value.get("metadata", {})
    phone_number_id = metadata.get("phone_number_id")
    user_id = await resolve_user(phone_number_id)
    if not user_id:
        return

    echoes = value.get("message_echoes") or value.get("messages") or []
    if not echoes:
        log.info("Echo sin mensajes (revisar estructura): %s", json.dumps(value)[:600])
        return

    for echo in echoes:
        wamid = echo.get("id")
        to_wa = echo.get("to") or echo.get("recipient_id")
        if not to_wa or (wamid and await already_processed(wamid)):
            continue
        body = echo.get("text", {}).get("body", "") if echo.get("type") == "text" else f"[{echo.get('type','mensaje')}]"

        contact = await upsert_contact(user_id, to_wa, None)
        conv = await get_or_create_conversation(user_id, contact, None, phone_number_id)
        await store_message(user_id, contact["id"], conv["id"], wamid or f"echo-{to_wa}", "out", "agent", body)
        await sb_patch("wa_conversations", {"id": f"eq.{conv['id']}"}, {"ai_enabled": False})


# =============================================================================
# 3) RECEPCIÓN (la IA)  ->  Anthropic, responde y califica de una
# =============================================================================
async def recepcion_responde(history: list, property_ctx: str | None) -> dict:
    contexto = property_ctx or (
        f"Atiendes prospectos de {DEFAULT_AGENCIA}, inmobiliaria en Morelia. "
        "Si no sabes por qué propiedad escribe, pregúntale qué busca."
    )
    system = (
        f"Eres 'Recepción', el asistente de WhatsApp de {DEFAULT_AGENCIA}, inmobiliaria en Morelia. "
        "Atiendes a un prospecto que escribió por un anuncio. Califícalo con calidez y rapidez, sin sonar "
        "a robot ni a interrogatorio: averigua forma de pago o crédito, presupuesto real, para cuándo lo "
        "necesita y qué busca; cuando haga sentido, ofrece agendar una visita con día y hora. Español "
        "mexicano, cálido y profesional, mensajes cortos de WhatsApp, sin emojis.\n\n"
        f"Contexto: {contexto}\n\n"
        "Responde ÚNICAMENTE con un JSON válido, sin texto antes ni después, así:\n"
        '{"reply":"el mensaje para el prospecto","temperatura":"Caliente|Tibio|Frío",'
        '"score":0-100,"presupuesto":"texto o null","forma_pago":"crédito|contado|por definir",'
        '"busca":"1 frase o null","listo_para_visita":true,"resumen":"1 frase para el agente"}'
    )

    # Anthropic exige que el hilo empiece en 'user': quitamos assistants iniciales
    msgs = list(history)
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if not msgs:
        msgs = [{"role": "user", "content": "Hola"}]

    try:
        async with httpx.AsyncClient(timeout=40) as c:
            r = await c.post(
                f"{ANTHROPIC_BASE}/messages",
                headers={"x-api-key": ANTHROPIC_API_KEY,
                         "anthropic-version": "2023-06-01",
                         "Content-Type": "application/json"},
                json={"model": RECEPCION_MODEL, "max_tokens": 600, "system": system, "messages": msgs},
            )
            data = r.json()
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
            return json.loads(text.replace("```json", "").replace("```", "").strip())
    except Exception as e:
        log.exception("Error en Recepción (Anthropic): %s", e)
        return {"reply": "¡Hola! Gracias por escribir. ¿Me cuentas qué estás buscando y para cuándo, "
                         "y con gusto te ayudo?",
                "temperatura": "Tibio", "score": 50, "presupuesto": None,
                "forma_pago": "por definir", "busca": None,
                "listo_para_visita": False, "resumen": "Prospecto nuevo, sin calificar aún."}


# =============================================================================
# 4) ENVÍO POR WHATSAPP (Cloud API)
# =============================================================================
async def wa_send_text(phone_number_id: str, to: str, body: str) -> dict:
    url = f"{GRAPH_API}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}}
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(url, headers=headers, json=data)
            if r.status_code >= 400:
                log.error("WhatsApp send error %s: %s", r.status_code, r.text)
            return r.json()
    except Exception as e:
        log.exception("Error enviando WhatsApp: %s", e)
        return {}


# =============================================================================
# 5) ENDPOINT PARA LA BANDEJA  ->  el agente manda un mensaje a mano
# =============================================================================
class SendReq(BaseModel):
    conversation_id: str
    body: str


@router.post("/send")
async def agent_send(req: SendReq, request: Request):
    user_id = await get_user_id_from_token(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sesión inválida")

    convs = await sb_get("wa_conversations",
                         {"id": f"eq.{req.conversation_id}", "user_id": f"eq.{user_id}", "limit": "1"})
    if not convs:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    conv = convs[0]

    cs = await sb_get("wa_contacts", {"id": f"eq.{conv['contact_id']}", "select": "wa_id", "limit": "1"})
    if not cs:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    to = cs[0]["wa_id"]

    sent = await wa_send_text(conv["phone_number_id"], to, req.body)
    out_id = (sent.get("messages") or [{}])[0].get("id")
    await store_message(user_id, conv["contact_id"], conv["id"],
                        out_id or f"agent-{_now()}", "out", "agent", req.body)
    # el humano contestó -> apagamos la IA en esta conversación
    await sb_patch("wa_conversations", {"id": f"eq.{conv['id']}"}, {"ai_enabled": False})
    return {"ok": True, "wa_message_id": out_id}


# =============================================================================
# 6) Funciones de datos
# =============================================================================
async def resolve_user(phone_number_id: str | None) -> str | None:
    if phone_number_id:
        rows = await sb_get("wa_numbers",
                            {"phone_number_id": f"eq.{phone_number_id}", "select": "user_id", "limit": "1"})
        if rows:
            return rows[0]["user_id"]
    return DEFAULT_USER_ID or None


async def already_processed(wamid: str) -> bool:
    rows = await sb_get("wa_messages", {"wa_message_id": f"eq.{wamid}", "select": "id", "limit": "1"})
    return bool(rows)


async def upsert_contact(user_id, wa_id, nombre):
    rows = await sb_get("wa_contacts",
                        {"user_id": f"eq.{user_id}", "wa_id": f"eq.{wa_id}", "limit": "1"})
    if rows:
        contact = rows[0]
        if nombre and not contact.get("nombre"):
            await sb_patch("wa_contacts", {"id": f"eq.{contact['id']}"}, {"nombre": nombre})
            contact["nombre"] = nombre
        return contact
    created = await sb_post("wa_contacts",
                            {"user_id": user_id, "wa_id": wa_id, "nombre": nombre,
                             "temperatura": "Nuevo", "score": 0, "etapa": "Nuevo"})
    return created[0] if created else {"id": None}


async def get_or_create_conversation(user_id, contact, referral, phone_number_id):
    rows = await sb_get("wa_conversations", {"contact_id": f"eq.{contact['id']}", "limit": "1"})
    if rows:
        return rows[0]
    property_ctx = None
    if referral:
        headline = referral.get("headline", "")
        bodytext = referral.get("body", "")
        property_ctx = f"El prospecto escribió por el anuncio: '{headline}'. {bodytext}".strip()
    created = await sb_post("wa_conversations",
                            {"user_id": user_id, "contact_id": contact["id"],
                             "phone_number_id": phone_number_id, "ai_enabled": True,
                             "property_ctx": property_ctx})
    return created[0] if created else {"id": None, "ai_enabled": True}


async def store_message(user_id, contact_id, conversation_id, wa_message_id, direction, sender, body):
    await sb_post("wa_messages",
                  {"user_id": user_id, "contact_id": contact_id, "conversation_id": conversation_id,
                   "wa_message_id": wa_message_id, "direction": direction, "sender": sender, "body": body},
                  prefer="return=minimal")
    await sb_patch("wa_conversations", {"id": f"eq.{conversation_id}"}, {"last_message_at": _now()})


async def fetch_history(conversation_id) -> list:
    rows = await sb_get("wa_messages",
                        {"conversation_id": f"eq.{conversation_id}", "select": "sender,body",
                         "order": "created_at.desc", "limit": str(HISTORY_LIMIT)})
    rows = list(reversed(rows or []))
    return [{"role": "user" if r["sender"] == "lead" else "assistant", "content": r["body"]} for r in rows]


async def actualizar_calificacion(contact_id, result: dict):
    if not result:
        return
    campos = {}
    for k in ("temperatura", "score", "presupuesto", "forma_pago", "busca", "resumen"):
        if result.get(k) is not None:
            campos[k] = result[k]
    if result.get("listo_para_visita"):
        campos["etapa"] = "Cita"
    if campos:
        campos["updated_at"] = _now()
        await sb_patch("wa_contacts", {"id": f"eq.{contact_id}"}, campos)


async def ai_sigue_encendida(conversation_id) -> bool:
    rows = await sb_get("wa_conversations",
                        {"id": f"eq.{conversation_id}", "select": "ai_enabled", "limit": "1"})
    return bool(rows) and rows[0].get("ai_enabled", True)
